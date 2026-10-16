import re
from datetime import datetime
from typing import Literal

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
    status: Literal["pending", "running", "completed", "failed"]
    workflow_type: str
    result: dict | None = None
    error_details: dict | None = None
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


class WorkflowExecutionResponse(BaseModel):
    """Response model for a single workflow execution."""

    id: str
    workflow_type: str
    status: Literal["pending", "running", "completed", "failed"]
    original_request: dict
    interpreted_request: dict | None = None
    result: dict | None = None
    error_details: dict | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class WorkflowListResponse(BaseModel):
    """Paginated response model for workflow list."""

    items: list[WorkflowExecutionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
