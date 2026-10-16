"""initial migration

Revision ID: 001
Revises:
Create Date: 2026-10-12 18:48:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                name="workflow_status",
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("original_request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("interpreted_request", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_executions"),
    )
    op.create_index(
        "ix_workflow_executions_status_created",
        "workflow_executions",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_executions_workflow_type"),
        "workflow_executions",
        ["workflow_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_executions_status"), "workflow_executions", ["status"], unique=False
    )

    op.create_table(
        "inbound_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processing_status", sa.String(length=50), nullable=False),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name="fk_inbound_events_workflow_execution_id_workflow_executions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inbound_events"),
        sa.UniqueConstraint(
            "source_system", "external_event_id", name="uq_inbound_events_source_external"
        ),
    )
    op.create_index(
        "ix_inbound_events_source_status",
        "inbound_events",
        ["source_system", "processing_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbound_events_source_system"), "inbound_events", ["source_system"], unique=False
    )
    op.create_index(
        op.f("ix_inbound_events_processing_status"),
        "inbound_events",
        ["processing_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inbound_events_workflow_execution_id"),
        "inbound_events",
        ["workflow_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inbound_events_workflow_execution_id"), table_name="inbound_events")
    op.drop_index(op.f("ix_inbound_events_processing_status"), table_name="inbound_events")
    op.drop_index(op.f("ix_inbound_events_source_system"), table_name="inbound_events")
    op.drop_index("ix_inbound_events_source_status", table_name="inbound_events")
    op.drop_table("inbound_events")
    op.drop_index(op.f("ix_workflow_executions_status"), table_name="workflow_executions")
    op.drop_index(op.f("ix_workflow_executions_workflow_type"), table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_status_created", table_name="workflow_executions")
    op.drop_table("workflow_executions")
    op.execute("DROP TYPE IF EXISTS workflow_status")
