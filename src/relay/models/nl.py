"""Natural Language models for order change interpretation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NLInterpretationRequest(BaseModel):
    """Request to interpret a natural language order change request."""

    text: str = Field(
        ..., min_length=1, max_length=2000, description="Natural language request text"
    )
    source_system: str = Field(
        ..., min_length=1, max_length=100, description="Source system identifier"
    )
    external_event_id: str = Field(
        ..., min_length=1, max_length=255, description="External event ID for deduplication"
    )
    customer_id: str | None = Field(
        None, min_length=1, max_length=100, description="Optional customer ID for validation"
    )


class OrderChangeRequestDraft(BaseModel):
    """Draft order change request extracted from natural language."""

    order_id: str = Field(..., min_length=1, max_length=100, description="Order identifier")
    requested_delivery_date: datetime
    customer_id: str | None = Field(
        None, min_length=1, max_length=100, description="Customer ID if mentioned"
    )

    @field_validator("requested_delivery_date", mode="before")
    @classmethod
    def parse_delivery_date(cls, v):
        if isinstance(v, str):
            # Handle various date formats
            v = v.replace("Z", "+00:00")
            # Try ISO format first
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
            # Try common formats
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(v, fmt)
                except ValueError:
                    continue
        return v


class NLInterpretationResponse(BaseModel):
    """Response from natural language interpretation."""

    success: bool
    draft: "OrderChangeRequestDraft | None" = None
    missing_fields: list[str] = Field(default_factory=list)
    ambiguities: list["AmbiguityDetail"] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    workflow_id: str | None = None
    invocation_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_ms: float | None = None

    model_config = ConfigDict(from_attributes=True)


class AmbiguityDetail(BaseModel):
    """Details about an ambiguity in the interpretation."""

    field: str
    message: str
    suggestions: list[str] = Field(default_factory=list)
