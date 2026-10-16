"""add_order_and_idempotency_tables

Revision ID: f3bde427f2bc
Revises: 31beac56c736
Create Date: 2026-10-14 18:25:27.680137+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3bde427f2bc"
down_revision: str | None = "31beac56c736"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create order_status enum
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
                CREATE TYPE order_status AS ENUM ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled');
            END IF;
        END $$;
    """)

    # Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.String(100), nullable=False),
        sa.Column("delivery_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')",
            name="ck_orders_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_orders"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"], unique=False)
    op.create_index("ix_orders_status", "orders", ["status"], unique=False)

    # Create idempotency_keys table
    op.create_table(
        "idempotency_keys",
        sa.Column("order_id", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("order_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name="fk_idempotency_keys_order_id_orders",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("order_id", "idempotency_key", name="pk_idempotency_keys"),
    )
    op.create_index("ix_idempotency_keys_order_id", "idempotency_keys", ["order_id"], unique=False)

    # Seed initial orders
    op.execute(
        """
        INSERT INTO orders (id, customer_id, delivery_date, status, created_at, updated_at)
        VALUES
            ('ORD-136D6350', 'customer-101', '2026-11-10 00:00:00+00', 'confirmed', NOW(), NOW()),
            ('ORD-61964039', 'customer-101', '2026-11-20 00:00:00+00', 'pending', NOW(), NOW()),
            ('ORD-C176AE39', 'customer-102', '2026-11-15 00:00:00+00', 'shipped', NOW(), NOW()),
            ('ORD-761CDE8F', 'customer-103', '2026-11-25 00:00:00+00', 'cancelled', NOW(), NOW()),
            ('ORD-04CAB142', 'customer-104', '2026-12-01 00:00:00+00', 'delivered', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_order_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")
    # Note: We don't drop the order_status enum type as it might be used elsewhere
