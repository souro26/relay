"""add_workflow_steps_and_telemetry

Revision ID: 4c8d19e53b21
Revises: f3bde427f2bc
Create Date: 2026-10-17 00:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c8d19e53b21"
down_revision: str | None = "f3bde427f2bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add telemetry columns to workflow_executions
    op.add_column(
        "workflow_executions",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("duration_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("failure_category", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_workflow_executions_correlation_id",
        "workflow_executions",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_executions_failure_category",
        "workflow_executions",
        ["failure_category"],
        unique=False,
    )

    # 2. Create workflow_steps table
    op.create_table(
        "workflow_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="started"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error_category", sa.String(length=100), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("step_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name="fk_workflow_steps_workflow_execution_id_workflow_executions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_steps"),
    )
    op.create_index(
        "ix_workflow_steps_workflow_execution_id",
        "workflow_steps",
        ["workflow_execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_steps_status",
        "workflow_steps",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_steps_execution_step",
        "workflow_steps",
        ["workflow_execution_id", "step_name", "attempt_number"],
        unique=False,
    )

    # 3. Create llm_invocations table
    op.create_table(
        "llm_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step_name", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="completed"),
        sa.Column("error_category", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name="fk_llm_invocations_workflow_execution_id_workflow_executions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_invocations"),
    )
    op.create_index(
        "ix_llm_invocations_workflow_execution_id",
        "llm_invocations",
        ["workflow_execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_llm_invocations_model",
        "llm_invocations",
        ["model"],
        unique=False,
    )
    op.create_index(
        "ix_llm_invocations_started_at",
        "llm_invocations",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_invocations_started_at", table_name="llm_invocations")
    op.drop_index("ix_llm_invocations_model", table_name="llm_invocations")
    op.drop_index("ix_llm_invocations_workflow_execution_id", table_name="llm_invocations")
    op.drop_table("llm_invocations")

    op.drop_index("ix_workflow_steps_execution_step", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_status", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_workflow_execution_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_index("ix_workflow_executions_failure_category", table_name="workflow_executions")
    op.drop_index("ix_workflow_executions_correlation_id", table_name="workflow_executions")
    op.drop_column("workflow_executions", "failure_category")
    op.drop_column("workflow_executions", "duration_ms")
    op.drop_column("workflow_executions", "started_at")
    op.drop_column("workflow_executions", "correlation_id")
