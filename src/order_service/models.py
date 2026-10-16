"""SQLAlchemy models for the Order Service.

These models replace the in-memory Pydantic models with persistent
PostgreSQL-backed storage using SQLAlchemy.
"""

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, field_validator
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relay.db.base import Base


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


def _order_status_values(enum_cls) -> list[str]:
    return [s.value for s in enum_cls]


class Order(Base):
    """Persistent order model stored in PostgreSQL."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    delivery_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(
            OrderStatus,
            name="order_status",
            create_constraint=True,
            validate_strings=True,
            values_callable=_order_status_values,
        ),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    idempotency_keys: Mapped[list["IdempotencyKey"]] = relationship(
        back_populates="order", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
    )


class IdempotencyKey(Base):
    """Idempotency key for deduplicating order updates.

    The composite key (order_id, idempotency_key) ensures that each
    idempotency key is unique per order, allowing the same key to be
    reused for different orders while preventing duplicate mutations
    for the same order.
    """

    __tablename__ = "idempotency_keys"

    order_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Store the complete order state at the time of the mutation
    order_state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    order: Mapped["Order"] = relationship(back_populates="idempotency_keys", lazy="selectin")

    __table_args__ = (Index("ix_idempotency_keys_order_id", "order_id"),)


# Pydantic models for API requests/responses (unchanged from before)


class OrderStatusEnum(enum.StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderCreate(BaseModel):
    customer_id: str
    delivery_date: datetime
    status: OrderStatusEnum = OrderStatusEnum.PENDING

    @field_validator("delivery_date", mode="before")
    @classmethod
    def parse_delivery_date(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class OrderUpdate(BaseModel):
    delivery_date: datetime | None = None
    status: OrderStatusEnum | None = None
    idempotency_key: str | None = None

    @field_validator("delivery_date", mode="before")
    @classmethod
    def parse_delivery_date(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


class OrderResponse(BaseModel):
    id: str
    customer_id: str
    delivery_date: datetime
    status: OrderStatusEnum
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_order(cls, order: "Order") -> "OrderResponse":
        return cls(
            id=order.id,
            customer_id=order.customer_id,
            delivery_date=order.delivery_date,
            status=OrderStatusEnum(order.status.value),
            created_at=order.created_at,
            updated_at=order.updated_at,
        )


class ErrorResponse(BaseModel):
    detail: str
    error_code: str
