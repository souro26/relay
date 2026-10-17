import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Order ID format from order service: ORD-XXXXXXXX (8 hex chars)
ORDER_ID_PATTERN = re.compile(r"^ORD-[0-9A-F]{8}$")


def _validate_order_id(v: str) -> str:
    """Validate that the string matches the order service ID format: ORD-XXXXXXXX."""
    if not ORDER_ID_PATTERN.match(v.upper()):
        raise ValueError("order_id must match format ORD-XXXXXXXX (8 hex characters)")
    return v


class OrderChangeRequest(BaseModel):
    source_system: str = Field(..., min_length=1, max_length=100)
    external_event_id: str = Field(..., min_length=1, max_length=255)
    customer_id: str = Field(..., min_length=1, max_length=100)
    order_id: str = Field(..., min_length=1, max_length=100)
    requested_delivery_date: datetime

    @field_validator("order_id", mode="before")
    @classmethod
    def validate_order_id(cls, v: str) -> str:
        return _validate_order_id(v)

    @field_validator("requested_delivery_date", mode="before")
    @classmethod
    def parse_delivery_date(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    def to_event_payload(self) -> dict:
        return self.model_dump(mode="json")


class OrderChangeResponse(BaseModel):
    execution_id: str
    status: str
    workflow_type: str
    result: dict | None = None
    error_details: dict | None = None
    correlation_id: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class WorkflowErrorCode(str):
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    CUSTOMER_ORDER_MISMATCH = "CUSTOMER_ORDER_MISMATCH"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    EXTERNAL_SERVICE_UNAVAILABLE = "EXTERNAL_SERVICE_UNAVAILABLE"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    EXTERNAL_SERVICE_TIMEOUT = "EXTERNAL_SERVICE_TIMEOUT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class WorkflowError(BaseModel):
    error_code: str
    message: str
    details: dict | None = None


class WorkflowStepDetail(BaseModel):
    id: str
    step_name: str
    attempt_number: int
    status: str
    started_at: str
    completed_at: str | None = None
    duration_ms: float | None = None
    error_category: str | None = None
    error_details: dict | None = None
    metadata: dict | None = None


class LLMInvocationDetail(BaseModel):
    id: str
    step_name: str | None = None
    provider: str
    model: str
    started_at: str
    completed_at: str | None = None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    status: str
    error_category: str | None = None
    error_message: str | None = None


class WorkflowExecutionResponse(BaseModel):
    """Response model for a single workflow execution."""

    id: str
    workflow_type: str
    status: str
    original_request: dict
    interpreted_request: dict | None = None
    result: dict | None = None
    error_details: dict | None = None
    failure_category: str | None = None
    correlation_id: str | None = None
    duration_ms: float | None = None
    order_id: str | None = None
    customer_id: str | None = None
    started_at: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class WorkflowDetailResponse(BaseModel):
    """Detailed response model for full workflow execution inspection."""

    id: str
    workflow_type: str
    status: str
    source_system: str | None = None
    external_event_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    order_id: str | None = None
    customer_id: str | None = None
    original_request: dict
    interpreted_request: dict | None = None
    result: dict | None = None
    error_details: dict | None = None
    failure_category: str | None = None
    started_at: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None
    duration_ms: float | None = None
    steps: list[WorkflowStepDetail] = Field(default_factory=list)
    llm_invocations: list[LLMInvocationDetail] = Field(default_factory=list)


class WorkflowListResponse(BaseModel):
    """Paginated response model for workflow list."""

    items: list[WorkflowExecutionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DashboardMetricsResponse(BaseModel):
    """Aggregated operational metrics computed directly from persistent storage."""

    total_workflows: int
    completed_workflows: int
    failed_workflows: int
    uncertain_workflows: int
    running_workflows: int
    pending_workflows: int
    success_rate: float | None = None
    success_rate_percentage: str
    median_duration_ms: float | None = None
    p95_duration_ms: float | None = None
    step_failure_counts: dict[str, int] = Field(default_factory=dict)
    total_llm_invocations: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: float = 0.0
    avg_llm_latency_ms: float | None = None
    recent_workflows: list[WorkflowExecutionResponse] = Field(default_factory=list)
