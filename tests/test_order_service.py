"""Regression tests for Order Service listing and idempotency datetime serialization."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from order_service.models import IdempotencyKey, Order, OrderStatus
from order_service.store import (
    _deserialize_order_state,
    _format_datetime,
    _parse_datetime,
    _serialize_order_state,
)


class TestDatetimeSerializationSemantics:
    """Unit tests for datetime serialization and deserialization helpers."""

    def test_format_and_parse_datetime_lossless(self):
        dt = datetime(2026, 11, 28, 14, 30, 45, 123456, tzinfo=UTC)
        serialized = _format_datetime(dt)
        assert isinstance(serialized, str)
        assert serialized == "2026-11-28T14:30:45.123456+00:00"

        parsed = _parse_datetime(serialized)
        assert isinstance(parsed, datetime)
        assert parsed == dt
        assert parsed.tzinfo is not None

    def test_serialize_and_deserialize_order_state(self):
        now = datetime.now(UTC)
        delivery = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
        serialized = _serialize_order_state(
            order_id="ORD-TEST",
            customer_id="cust-1",
            delivery_date=delivery,
            status=OrderStatus.CONFIRMED,
            created_at=now,
            updated_at=now,
        )

        assert isinstance(serialized, dict)
        assert isinstance(serialized["delivery_date"], str)
        assert isinstance(serialized["created_at"], str)
        assert isinstance(serialized["updated_at"], str)
        assert serialized["status"] == "confirmed"

        # Reconstructed Order must have datetime instances
        reconstructed = _deserialize_order_state(serialized)
        assert isinstance(reconstructed, Order)
        assert reconstructed.id == "ORD-TEST"
        assert isinstance(reconstructed.delivery_date, datetime)
        assert isinstance(reconstructed.created_at, datetime)
        assert isinstance(reconstructed.updated_at, datetime)
        assert reconstructed.status == OrderStatus.CONFIRMED


@pytest.mark.integration
class TestOrderServiceListingIntegration:
    """Integration tests for GET /orders against real PostgreSQL."""

    def test_unfiltered_order_listing_returns_all_orders(self, pg_integration_order_client):
        response = pg_integration_order_client.get("/orders")
        assert response.status_code == 200
        orders = response.json()
        assert isinstance(orders, list)
        assert len(orders) >= 5  # Seeded orders exist

        ids = [o["id"] for o in orders]
        assert "ORD-136D6350" in ids
        assert "ORD-61964039" in ids

    def test_customer_filtered_order_listing(self, pg_integration_order_client):
        response = pg_integration_order_client.get("/orders?customer_id=customer-101")
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) >= 2
        for order in orders:
            assert order["customer_id"] == "customer-101"

    def test_unknown_customer_returns_empty_list(self, pg_integration_order_client):
        response = pg_integration_order_client.get("/orders?customer_id=customer-unknown-999")
        assert response.status_code == 200
        orders = response.json()
        assert orders == []


@pytest.mark.integration
class TestIdempotencyJsonbAndReplayIntegration:
    """Integration tests for JSONB idempotency persistence and replay in PostgreSQL."""

    def test_jsonb_persistence_with_datetime_values(
        self, pg_integration_order_client, pg_integration_db_session
    ):
        patch_payload = {
            "delivery_date": "2026-11-29T00:00:00Z",
            "idempotency_key": "pg_idem_jsonb_001",
        }
        response = pg_integration_order_client.patch(
            "/orders/ORD-61964039",
            json=patch_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ORD-61964039"
        assert "2026-11-29" in data["delivery_date"]

        # Verify the raw JSONB record in PostgreSQL
        ik = pg_integration_db_session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.order_id == "ORD-61964039",
                IdempotencyKey.idempotency_key == "pg_idem_jsonb_001",
            )
        ).scalar_one_or_none()

        assert ik is not None
        assert isinstance(ik.order_state, dict)
        assert isinstance(ik.order_state["delivery_date"], str)
        assert "2026-11-29" in ik.order_state["delivery_date"]
        assert isinstance(ik.order_state["created_at"], str)
        assert isinstance(ik.order_state["updated_at"], str)

    def test_idempotency_replay_returns_stored_result(self, pg_integration_order_client):
        patch_payload = {
            "delivery_date": "2026-11-30T00:00:00Z",
            "idempotency_key": "pg_idem_replay_002",
        }
        # First request
        resp1 = pg_integration_order_client.patch("/orders/ORD-61964039", json=patch_payload)
        assert resp1.status_code == 200
        data1 = resp1.json()

        # Second request with identical idempotency key
        resp2 = pg_integration_order_client.patch("/orders/ORD-61964039", json=patch_payload)
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data1["delivery_date"] == data2["delivery_date"]
        assert data1["updated_at"] == data2["updated_at"]
        assert data1["id"] == data2["id"]

    def test_shipped_order_invalid_transition_conflict(self, pg_integration_order_client):
        # ORD-C176AE39 is SHIPPED
        patch_payload = {
            "delivery_date": "2026-11-28T00:00:00Z",
            "idempotency_key": "new_key_on_shipped_order",
        }
        response = pg_integration_order_client.patch("/orders/ORD-C176AE39", json=patch_payload)
        assert response.status_code == 409
        err = response.json()
        assert err["detail"]["error_code"] == "INVALID_STATE_TRANSITION"
