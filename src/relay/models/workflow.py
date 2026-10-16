import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from relay.db.base import Base


class WorkflowStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    EXTERNAL_OPERATION_PENDING = "external_operation_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


def _workflow_status_values(enum_cls) -> list[str]:
    return [s.value for s in enum_cls]


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[WorkflowStatus] = mapped_column(
        SQLEnum(
            WorkflowStatus,
            name="workflow_status",
            create_constraint=True,
            validate_strings=True,
            values_callable=_workflow_status_values,
        ),
        nullable=False,
        default=WorkflowStatus.PENDING,
        index=True,
    )
    original_request: Mapped[dict] = mapped_column(JSONB, nullable=False)
    interpreted_request: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Idempotency key for the external operation (order service)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    inbound_events: Mapped[list["InboundEvent"]] = relationship(
        back_populates="workflow_execution", lazy="selectin"
    )
    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow_execution",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.started_at",
    )
    llm_invocations: Mapped[list["LLMInvocation"]] = relationship(
        back_populates="workflow_execution",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="LLMInvocation.started_at",
    )

    __table_args__ = (
        Index("ix_workflow_executions_status_created", "status", "created_at"),
    )


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt_number: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="started", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    step_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    workflow_execution: Mapped["WorkflowExecution"] = relationship(
        back_populates="steps"
    )

    __table_args__ = (
        Index(
            "ix_workflow_steps_execution_step",
            "workflow_execution_id",
            "step_name",
            "attempt_number",
        ),
    )


class LLMInvocation(Base):
    __tablename__ = "llm_invocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    step_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="completed")
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    workflow_execution: Mapped[WorkflowExecution | None] = relationship(
        back_populates="llm_invocations"
    )

    __table_args__ = (
        Index("ix_llm_invocations_model", "model"),
        Index("ix_llm_invocations_started_at", "started_at"),
    )


class InboundEvent(Base):
    __tablename__ = "inbound_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processing_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="received", index=True
    )
    workflow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    workflow_execution: Mapped[WorkflowExecution | None] = relationship(
        back_populates="inbound_events", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_system", "external_event_id", name="uq_inbound_events_source_external"
        ),
        Index("ix_inbound_events_source_status", "source_system", "processing_status"),
    )
