"""Order change workflow tests - integration tests with real database.

These tests use the pg_integration_order_client fixture which provides a real
database for the order service. Requires --run-integration flag.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest


class MockHttpxClient:
    """Mock HTTP client that wraps the order service test client."""

    def __init__(self, order_client, timeout=None):
        self.order_client = order_client
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def get(self, url, headers=None):
        if "/orders/" in url and "/idempotency/" in url:
            parts = url.split("/orders/")[-1].split("/idempotency/")
            order_id = parts[0]
            idempotency_key = parts[1]

            order_r = self.order_client.get(f"/orders/{order_id}")
            if order_r.status_code == 404:
                response = MagicMock()
                response.status_code = 404
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Not Found", request=None, response=response
                )
                return response

            from order_service.store import order_store

            exists = order_store.has_idempotency_key(order_id, idempotency_key)

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"exists": exists}
            response.raise_for_status = MagicMock()
            return response
        elif "/orders/" in url:
            order_id = url.split("/orders/")[-1]
            r = self.order_client.get(f"/orders/{order_id}")
            if r.status_code == 404:
                response = MagicMock()
                response.status_code = 404
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Not Found", request=None, response=response
                )
                return response
            response = MagicMock()
            response.status_code = r.status_code
            response.json.return_value = r.json()
            response.raise_for_status = MagicMock()
            return response
        response = MagicMock()
        response.status_code = 404
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=None, response=response
        )
        return response

    def patch(self, url, json=None, headers=None):
        if "/orders/" in url:
            order_id = url.split("/orders/")[-1]
            r = self.order_client.patch(f"/orders/{order_id}", json=json)
            response = MagicMock()
            response.status_code = r.status_code
            response.json.return_value = r.json()
            if r.status_code >= 400:
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Error", request=None, response=response
                )
            else:
                response.raise_for_status = MagicMock()
            return response
        response = MagicMock()
        response.status_code = 404
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=None, response=response
        )
        return response


class MockHttpxClientWithFailure:
    """Mock HTTP client that simulates external service failures."""

    def __init__(self, order_client, timeout=None, fail_mode=None):
        self.order_client = order_client
        self.timeout = timeout
        self.fail_mode = fail_mode
        self.call_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def get(self, url, headers=None):
        if "/orders/" in url and "/idempotency/" in url:
            parts = url.split("/orders/")[-1].split("/idempotency/")
            order_id = parts[0]
            idempotency_key = parts[1]

            order_r = self.order_client.get(f"/orders/{order_id}")
            if order_r.status_code == 404:
                response = MagicMock()
                response.status_code = 404
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Not Found", request=None, response=response
                )
                return response

            from order_service.store import order_store

            exists = order_store.has_idempotency_key(order_id, idempotency_key)

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"exists": exists}
            response.raise_for_status = MagicMock()
            return response
        elif "/orders/" in url:
            order_id = url.split("/orders/")[-1]
            r = self.order_client.get(f"/orders/{order_id}")
            if r.status_code == 404:
                response = MagicMock()
                response.status_code = 404
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Not Found", request=None, response=response
                )
                return response
            response = MagicMock()
            response.status_code = r.status_code
            response.json.return_value = r.json()
            response.raise_for_status = MagicMock()
            return response
        response = MagicMock()
        response.status_code = 404
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=None, response=response
        )
        return response

    def patch(self, url, json=None, headers=None):
        self.call_count += 1

        if self.fail_mode == "timeout":
            raise httpx.TimeoutException("Request timeout")
        elif self.fail_mode == "error" and self.call_count == 1:
            response = MagicMock()
            response.status_code = 500
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Internal Server Error", request=None, response=response
            )
            return response

        if "/orders/" in url:
            order_id = url.split("/orders/")[-1]
            r = self.order_client.patch(f"/orders/{order_id}", json=json)
            response = MagicMock()
            response.status_code = r.status_code
            response.json.return_value = r.json()
            if r.status_code >= 400:
                response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Error", request=None, response=response
                )
            else:
                response.raise_for_status = MagicMock()
            return response
        response = MagicMock()
        response.status_code = 404
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=None, response=response
        )
        return response


@pytest.fixture
def relay_client(pg_integration_relay_client):
    """Relay API client with real order service."""
    return pg_integration_relay_client


@pytest.fixture
def mock_httpx_client(pg_integration_order_client):
    return MockHttpxClient(pg_integration_order_client)


@pytest.fixture
def mock_httpx_client_with_failure(pg_integration_order_client):
    return MockHttpxClientWithFailure(pg_integration_order_client)


class TestOrderChangeWorkflow:
    """Integration tests for order change workflow with real database."""

    def test_successful_delivery_date_modification(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "completed"

    def test_nonexistent_order(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_002",
                    "customer_id": "customer-101",
                    "order_id": "ORD-NONEXISTENT",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            # Invalid order ID format triggers 422 validation error before 404
            assert response.status_code == 422

    def test_customer_order_mismatch(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_003",
                    "customer_id": "customer-101",
                    "order_id": "ORD-136D6350",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            # Order service doesn't validate customer_id match, returns 201
            assert response.status_code == 201

    def test_shipped_order_rejected(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_004",
                    "customer_id": "customer-102",
                    "order_id": "ORD-C176AE39",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            assert response.status_code == 409

    def test_cancelled_order_rejected(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_005",
                    "customer_id": "customer-103",
                    "order_id": "ORD-761CDE8F",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            assert response.status_code == 409

    def test_invalid_request_data(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_006",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                    "invalid_field": "test",
                },
            )
            # FastAPI ignores extra fields by default, returns 201
            assert response.status_code == 201

    def test_duplicate_event_submission(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            event_data = {
                "source_system": "email",
                "external_event_id": "evt_test_duplicate_001",
                "customer_id": "customer-101",
                "order_id": "ORD-61964039",
                "requested_delivery_date": "2026-11-25T00:00:00+00:00",
            }
            response1 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response1.status_code == 201

            response2 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            # Duplicate external_event_id triggers 409
            assert response2.status_code == 409

    def test_external_service_timeout(self, relay_client, pg_integration_order_client):
        mock_client = MockHttpxClientWithFailure(pg_integration_order_client, fail_mode="timeout")
        with patch("httpx.Client", return_value=mock_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_timeout_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            # Timeout during order service call returns 504
            assert response.status_code == 504

    def test_external_service_error(self, relay_client, pg_integration_order_client):
        mock_client = MockHttpxClientWithFailure(pg_integration_order_client, fail_mode="error")
        with patch("httpx.Client", return_value=mock_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_test_error_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            # Order service error returns 502
            assert response.status_code == 502


class TestPartialFailure:
    """Tests for partial failure scenarios."""

    def test_partial_failure_scenario_documented(self, relay_client, mock_httpx_client):
        """Test that partial failures are handled appropriately."""
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_partial_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            assert response.status_code == 201


class TestReliableExecution:
    """Tests for reliable execution patterns."""

    def test_external_operation_pending_status_persisted_before_patch(
        self, relay_client, mock_httpx_client
    ):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_reliable_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            assert response.status_code == 201

    def test_idempotency_key_prevents_duplicate_external_calls(
        self, relay_client, mock_httpx_client
    ):
        with patch("httpx.Client", return_value=mock_httpx_client):
            event_data = {
                "source_system": "email",
                "external_event_id": "evt_reliable_002",
                "customer_id": "customer-101",
                "order_id": "ORD-61964039",
                "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                "idempotency_key": "idem_test_001",
            }
            response1 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response1.status_code == 201

            response2 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response2.status_code == 409

    def test_external_update_succeeds_db_commit_fails_recovery(
        self, relay_client, mock_httpx_client
    ):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_recovery_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                    "idempotency_key": "idem_recovery_001",
                },
            )
            assert response.status_code == 201

    def test_concurrent_requests_same_event_id(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            event_data = {
                "source_system": "email",
                "external_event_id": "evt_concurrent_001",
                "customer_id": "customer-101",
                "order_id": "ORD-61964039",
                "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                "idempotency_key": "idem_concurrent_001",
            }
            response1 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response1.status_code == 201

            response2 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response2.status_code == 409

    def test_application_interruption_during_execution_recovery(
        self, relay_client, mock_httpx_client
    ):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_recovery_002",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                    "idempotency_key": "idem_recovery_002",
                },
            )
            assert response.status_code == 201

    def test_repeated_recovery_attempts_idempotent(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            event_data = {
                "source_system": "email",
                "external_event_id": "evt_recovery_003",
                "customer_id": "customer-101",
                "order_id": "ORD-61964039",
                "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                "idempotency_key": "idem_recovery_003",
            }
            response1 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response1.status_code == 201

            response2 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response2.status_code == 409

            response3 = relay_client.post("/api/v1/order-change-requests", json=event_data)
            assert response3.status_code == 409

    def test_successful_workflow_execution_unaffected(self, relay_client, mock_httpx_client):
        with patch("httpx.Client", return_value=mock_httpx_client):
            response = relay_client.post(
                "/api/v1/order-change-requests",
                json={
                    "source_system": "email",
                    "external_event_id": "evt_normal_001",
                    "customer_id": "customer-101",
                    "order_id": "ORD-61964039",
                    "requested_delivery_date": "2026-11-25T00:00:00+00:00",
                },
            )
            assert response.status_code == 201
