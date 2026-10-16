"""PostgreSQL-backed order store with persistent idempotency keys."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from order_service.db import get_session
from order_service.models import IdempotencyKey, Order, OrderStatus, OrderUpdate

if TYPE_CHECKING:
    pass


def _format_datetime(dt: datetime | str | None) -> str | None:
    """Serialize datetime to ISO 8601 string with UTC timezone."""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _parse_datetime(val: datetime | str | None) -> datetime | None:
    """Deserialize ISO 8601 string to timezone-aware datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(val)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _serialize_order_state(
    order_id: str,
    customer_id: str,
    delivery_date: datetime | str,
    status: OrderStatus | str,
    created_at: datetime | str,
    updated_at: datetime | str,
) -> dict:
    """Lossless serialization of order state dictionary for JSONB storage."""
    status_str = status.value if hasattr(status, "value") else str(status)
    return {
        "id": order_id,
        "customer_id": customer_id,
        "delivery_date": _format_datetime(delivery_date),
        "status": status_str,
        "created_at": _format_datetime(created_at),
        "updated_at": _format_datetime(updated_at),
    }


def _deserialize_order_state(state: dict) -> Order:
    """Reconstruct an Order instance from stored JSONB order_state."""
    return Order(
        id=state["id"],
        customer_id=state["customer_id"],
        delivery_date=_parse_datetime(state["delivery_date"]),
        status=OrderStatus(state["status"]),
        created_at=_parse_datetime(state["created_at"]),
        updated_at=_parse_datetime(state["updated_at"]),
    )


class OrderStore:
    """PostgreSQL-backed order store with durable idempotency keys."""

    def reset(self) -> None:
        """Reset the store to initial seed data."""
        with get_session() as session:
            session.execute(delete(IdempotencyKey))
            session.execute(delete(Order))
            session.commit()
            self._seed_orders(session)

    def _seed_orders(self, session: Session) -> None:
        """Seed the database with initial orders if empty."""
        existing = session.execute(select(Order).limit(1)).first()
        if existing:
            return

        seed_data = [
            {
                "id": "ORD-136D6350",
                "customer_id": "customer-101",
                "delivery_date": datetime(2026, 11, 10, tzinfo=UTC),
                "status": OrderStatus.CONFIRMED,
            },
            {
                "id": "ORD-61964039",
                "customer_id": "customer-101",
                "delivery_date": datetime(2026, 11, 20, tzinfo=UTC),
                "status": OrderStatus.PENDING,
            },
            {
                "id": "ORD-C176AE39",
                "customer_id": "customer-102",
                "delivery_date": datetime(2026, 11, 15, tzinfo=UTC),
                "status": OrderStatus.SHIPPED,
            },
            {
                "id": "ORD-761CDE8F",
                "customer_id": "customer-103",
                "delivery_date": datetime(2026, 11, 25, tzinfo=UTC),
                "status": OrderStatus.CANCELLED,
            },
            {
                "id": "ORD-04CAB142",
                "customer_id": "customer-104",
                "delivery_date": datetime(2026, 12, 1, tzinfo=UTC),
                "status": OrderStatus.DELIVERED,
            },
        ]
        for data in seed_data:
            order = Order(**data)
            session.add(order)
        session.commit()

    def get_order(self, order_id: str) -> Order | None:
        with get_session() as session:
            return session.get(Order, order_id)

    def list_orders(self, customer_id: str | None = None) -> list[Order]:
        """List orders from PostgreSQL, optionally filtered by customer_id."""
        with get_session() as session:
            stmt = select(Order)
            if customer_id:
                stmt = stmt.where(Order.customer_id == customer_id)
            return list(session.execute(stmt).scalars().all())

    def update_order(self, order_id: str, update: OrderUpdate) -> Order | None:
        with get_session() as session:
            # Use SELECT FOR UPDATE to lock the row for the duration of the transaction
            order = session.execute(
                select(Order).where(Order.id == order_id).with_for_update()
            ).scalar_one_or_none()

            if order is None:
                return None

            # Check idempotency key first
            if update.idempotency_key:
                existing_key = session.execute(
                    select(IdempotencyKey).where(
                        IdempotencyKey.order_id == order_id,
                        IdempotencyKey.idempotency_key == update.idempotency_key,
                    )
                ).scalar_one_or_none()

                if existing_key:
                    # Reconstruct the order from the stored state preserving datetime semantics
                    return _deserialize_order_state(existing_key.order_state)

            if order.status in (OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.DELIVERED):
                if update.delivery_date is not None:
                    return None

            # Compute the new order state first (without modifying the original)
            new_delivery_date = (
                update.delivery_date if update.delivery_date is not None else order.delivery_date
            )
            new_status = update.status if update.status is not None else order.status
            new_updated_at = datetime.now(UTC)

            # Check if the update would actually change anything
            if new_delivery_date == order.delivery_date and new_status == order.status:
                # No change - but still store idempotency key if provided
                if update.idempotency_key:
                    ik = IdempotencyKey(
                        order_id=order_id,
                        idempotency_key=update.idempotency_key,
                        order_state=_serialize_order_state(
                            order.id,
                            order.customer_id,
                            order.delivery_date,
                            order.status,
                            order.created_at,
                            order.updated_at,
                        ),
                    )
                    session.add(ik)
                    session.commit()
                return order

            # Create the new order state for idempotency storage with ISO 8601 serialized datetimes
            new_order_state = _serialize_order_state(
                order.id,
                order.customer_id,
                new_delivery_date,
                new_status,
                order.created_at,
                new_updated_at,
            )

            # Store the new state in idempotency store FIRST (before mutating the original)
            if update.idempotency_key:
                ik = IdempotencyKey(
                    order_id=order_id,
                    idempotency_key=update.idempotency_key,
                    order_state=new_order_state,
                )
                session.add(ik)

            # Now apply the changes to the actual order
            order.delivery_date = new_delivery_date
            order.status = new_status
            order.updated_at = new_updated_at

            session.commit()
            return order

    def get_orders_by_customer(self, customer_id: str) -> list[Order]:
        return self.list_orders(customer_id)

    def has_idempotency_key(self, order_id: str, idempotency_key: str) -> bool:
        """Check if an idempotency key exists for an order."""
        with get_session() as session:
            return (
                session.execute(
                    select(IdempotencyKey).where(
                        IdempotencyKey.order_id == order_id,
                        IdempotencyKey.idempotency_key == idempotency_key,
                    )
                ).first()
                is not None
            )


order_store = OrderStore()
