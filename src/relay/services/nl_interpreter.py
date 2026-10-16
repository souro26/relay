"""Natural language interpretation service for order change requests."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from relay.adapters.llm import (
    LLMAdapter,
    LLMConfigurationError,
    LLMOutputParseError,
    LLMProviderError,
    LLMTimeoutError,
)
from relay.core.config import estimate_llm_cost, settings
from relay.core.logging import log_llm_call
from relay.models import LLMInvocation
from relay.models.nl import (
    AmbiguityDetail,
    NLInterpretationRequest,
    NLInterpretationResponse,
    OrderChangeRequestDraft,
)
from relay.prompts.order_change import (
    FEW_SHOT_EXAMPLES,
    PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    get_response_schema,
)

logger = logging.getLogger(__name__)


class NLInterpretationError(Exception):
    """Exception raised when NL interpretation fails."""

    def __init__(
        self,
        message: str,
        error_code: str,
        missing_fields: list[str] | None = None,
        ambiguities: list[dict] | None = None,
    ):
        self.message = message
        self.error_code = error_code
        self.missing_fields = missing_fields or []
        self.ambiguities = ambiguities or []
        super().__init__(message)


class NLInterpreterService:
    """Service for interpreting natural language order change requests."""

    def __init__(self, llm_adapter: LLMAdapter | None = None):
        """
        Initialize the NL interpreter service.

        Args:
            llm_adapter: Optional LLM adapter. If not provided, uses the
                configured adapter from settings.
        """
        self._llm_adapter: LLMAdapter | None = llm_adapter

    async def _get_adapter(self) -> LLMAdapter:
        """Get the LLM adapter, creating it if needed."""
        if self._llm_adapter is None:
            try:
                from relay.adapters.llm import get_llm_adapter

                self._llm_adapter = get_llm_adapter()
            except LLMConfigurationError:
                raise
            except Exception as e:
                raise RuntimeError(f"LLM adapter not configured: {e}") from e
        return self._llm_adapter

    async def interpret(
        self,
        request: NLInterpretationRequest,
        db: Session | None = None,
        workflow_execution_id: uuid.UUID | None = None,
    ) -> NLInterpretationResponse:
        """
        Interpret a natural language order change request with durable telemetry.

        Args:
            request: The natural language interpretation request.
            db: Optional SQLAlchemy session for persisting LLM telemetry.
            workflow_execution_id: Optional workflow execution ID to link telemetry.

        Returns:
            NLInterpretationResponse with either a valid draft or error details.
        """
        # Validate input size
        if len(request.text) > settings.llm_max_input_chars:
            logger.warning(
                "NL request text exceeds max input size",
                extra={
                    "input_length": len(request.text),
                    "max_allowed": settings.llm_max_input_chars,
                },
            )
            return NLInterpretationResponse(
                success=False,
                error=f"Request text too long (max {settings.llm_max_input_chars} characters)",
                error_code="INPUT_TOO_LARGE",
            )

        try:
            adapter = await self._get_adapter()
        except LLMConfigurationError as e:
            logger.error("LLM configuration error: %s", e)
            return NLInterpretationResponse(
                success=False,
                error=(
                    "Natural language interpretation is not configured. "
                    "Set LLM_API_KEY environment variable to enable."
                ),
                error_code="LLM_NOT_CONFIGURED",
            )

        # Check if LLM is configured (only if we needed to create the adapter)
        if self._llm_adapter is None and not settings.llm_api_key:
            return NLInterpretationResponse(
                success=False,
                error=(
                    "Natural language interpretation is not configured. "
                    "Set LLM_API_KEY environment variable to enable."
                ),
                error_code="LLM_NOT_CONFIGURED",
            )

        # Build prompt
        prompt = self._build_prompt(request.text)
        start_mono = time.monotonic()
        start_utc = datetime.now(UTC)

        try:
            # Call LLM with structured output
            llm_response = await adapter.complete(
                prompt=prompt,
                system_prompt=None,  # Included in prompt
                temperature=0.0,
                max_tokens=settings.llm_max_output_tokens,
                response_format=get_response_schema(),
            )
            latency_ms = (time.monotonic() - start_mono) * 1000

            prompt_tokens = llm_response.usage.prompt_tokens if llm_response.usage else None
            comp_tokens = llm_response.usage.completion_tokens if llm_response.usage else None
            total_tokens = llm_response.usage.total_tokens if llm_response.usage else None
            estimated_cost = estimate_llm_cost(prompt_tokens, comp_tokens)

            invocation_id = None
            if db is not None:
                try:
                    invocation = LLMInvocation(
                        workflow_execution_id=workflow_execution_id,
                        step_name="natural_language_interpretation",
                        provider=getattr(adapter, "provider_name", "unknown"),
                        model=getattr(adapter, "model_name", settings.llm_model),
                        started_at=start_utc,
                        completed_at=datetime.now(UTC),
                        latency_ms=round(latency_ms, 2),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=comp_tokens,
                        total_tokens=total_tokens,
                        estimated_cost_usd=estimated_cost,
                        status="completed",
                    )
                    db.add(invocation)
                    db.flush()
                    invocation_id = str(invocation.id)
                except Exception as save_err:
                    logger.warning("Failed to persist LLM invocation record: %s", save_err)

            log_llm_call(
                logger,
                model=getattr(adapter, "model_name", settings.llm_model),
                prompt_tokens=prompt_tokens,
                completion_tokens=comp_tokens,
                total_tokens=total_tokens,
                duration_ms=latency_ms,
                estimated_cost_usd=estimated_cost,
            )

            # Parse structured output
            parsed = self._parse_response(llm_response.content)
            parsed.invocation_id = invocation_id
            parsed.prompt_tokens = prompt_tokens
            parsed.completion_tokens = comp_tokens
            parsed.total_tokens = total_tokens
            parsed.estimated_cost_usd = estimated_cost
            parsed.latency_ms = round(latency_ms, 2)
            return parsed

        except LLMConfigurationError as e:
            logger.error("LLM configuration error: %s", e)
            return NLInterpretationResponse(
                success=False,
                error=(
                    "Natural language interpretation is not configured. "
                    "Set LLM_API_KEY environment variable to enable."
                ),
                error_code="LLM_NOT_CONFIGURED",
            )
        except LLMTimeoutError as e:
            latency_ms = (time.monotonic() - start_mono) * 1000
            self._record_failed_invocation(
                db, workflow_execution_id, adapter, start_utc, latency_ms, "LLM_TIMEOUT", str(e)
            )
            logger.warning("LLM request timed out: %s", e)
            return NLInterpretationResponse(
                success=False,
                error="Interpretation request timed out. Please try again.",
                error_code="LLM_TIMEOUT",
                latency_ms=round(latency_ms, 2),
            )
        except LLMProviderError as e:
            latency_ms = (time.monotonic() - start_mono) * 1000
            if e.status_code == 429:
                error_code = "LLM_RATE_LIMIT"
                message = "LLM provider rate limit exceeded. Please try again later."
            elif e.status_code and 500 <= e.status_code < 600:
                error_code = "LLM_PROVIDER_ERROR"
                message = "LLM provider temporarily unavailable. Please try again later."
            else:
                error_code = "LLM_PROVIDER_ERROR"
                message = "LLM provider error. Please try again later."

            self._record_failed_invocation(
                db, workflow_execution_id, adapter, start_utc, latency_ms, error_code, str(e)
            )
            logger.warning("LLM provider error: %s (status: %s)", e, e.status_code)
            return NLInterpretationResponse(
                success=False,
                error=message,
                error_code=error_code,
                latency_ms=round(latency_ms, 2),
            )
        except LLMOutputParseError as e:
            latency_ms = (time.monotonic() - start_mono) * 1000
            self._record_failed_invocation(
                db,
                workflow_execution_id,
                adapter,
                start_utc,
                latency_ms,
                "LLM_OUTPUT_PARSE_ERROR",
                str(e),
            )
            logger.warning("Failed to parse LLM output: %s", e)
            return NLInterpretationResponse(
                success=False,
                error="Failed to parse interpretation result. Please try again.",
                error_code="LLM_OUTPUT_PARSE_ERROR",
                latency_ms=round(latency_ms, 2),
            )
        except Exception as e:
            latency_ms = (time.monotonic() - start_mono) * 1000
            self._record_failed_invocation(
                db,
                workflow_execution_id,
                adapter,
                start_utc,
                latency_ms,
                "INTERNAL_ERROR",
                str(e),
            )
            logger.exception("Unexpected error during NL interpretation")
            return NLInterpretationResponse(
                success=False,
                error="Internal error during interpretation. Please try again.",
                error_code="INTERNAL_ERROR",
                latency_ms=round(latency_ms, 2),
            )

    def _record_failed_invocation(
        self,
        db: Session | None,
        workflow_execution_id: uuid.UUID | None,
        adapter: Any,
        start_utc: datetime,
        latency_ms: float,
        error_category: str,
        error_message: str,
    ) -> None:
        """Safely record failed invocation in database and log."""
        model_name = (
            getattr(adapter, "model_name", settings.llm_model) if adapter else settings.llm_model
        )
        provider_name = (
            getattr(adapter, "provider_name", "unknown") if adapter else settings.llm_provider
        )
        log_llm_call(
            logger,
            model=model_name,
            duration_ms=latency_ms,
            error=error_message,
            error_category=error_category,
        )
        if db is not None:
            try:
                invocation = LLMInvocation(
                    workflow_execution_id=workflow_execution_id,
                    step_name="natural_language_interpretation",
                    provider=provider_name,
                    model=model_name,
                    started_at=start_utc,
                    completed_at=datetime.now(UTC),
                    latency_ms=round(latency_ms, 2),
                    status="failed",
                    error_category=error_category,
                    error_message=error_message[:500],
                )
                db.add(invocation)
                db.flush()
            except Exception as err:
                logger.warning("Failed to persist failed LLM invocation record: %s", err)

    def _parse_response(self, response_text: str) -> NLInterpretationResponse:
        """
        Parse and validate the LLM response.

        Args:
            response_text: Raw response text from the LLM.

        Returns:
            Validated NLInterpretationResponse.
        """
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM JSON output: %s", e)
            return NLInterpretationResponse(
                success=False,
                error="Invalid JSON response from interpreter",
                error_code="LLM_OUTPUT_PARSE_ERROR",
            )

        # Validate required fields
        if not isinstance(data.get("success"), bool):
            return NLInterpretationResponse(
                success=False,
                error="Invalid interpretation result: missing 'success' field",
                error_code="LLM_OUTPUT_PARSE_ERROR",
            )

        if data.get("success"):
            draft_data = data.get("draft")
            if not draft_data:
                return NLInterpretationResponse(
                    success=False,
                    error="Missing draft in successful interpretation",
                    error_code="LLM_OUTPUT_PARSE_ERROR",
                )

            try:
                draft = OrderChangeRequestDraft(**draft_data)
            except Exception as e:
                logger.warning("Invalid draft in LLM output: %s", e)
                return NLInterpretationResponse(
                    success=False,
                    error="Invalid draft structure in interpretation",
                    error_code="LLM_OUTPUT_PARSE_ERROR",
                )

            # Convert ambiguities to AmbiguityDetail objects for success case too
            ambiguities_data = data.get("ambiguities", [])
            ambiguities = []
            for amb in ambiguities_data:
                if isinstance(amb, dict):
                    ambiguities.append(AmbiguityDetail(**amb))
                else:
                    ambiguities.append(AmbiguityDetail(field="", message=str(amb)))

            return NLInterpretationResponse(
                success=True,
                draft=draft,
                missing_fields=data.get("missing_fields", []),
                ambiguities=ambiguities,
                error=None,
                error_code=None,
            )
        else:
            # Failed interpretation
            error_code = data.get("error_code") or "VALIDATION_ERROR"
            _ = data.get("error") or "Interpretation failed"
            missing_fields = data.get("missing_fields", [])
            ambiguities_data = data.get("ambiguities", [])

            # Convert ambiguities to AmbiguityDetail objects
            ambiguities = []
            for amb in ambiguities_data:
                if isinstance(amb, dict):
                    ambiguities.append(AmbiguityDetail(**amb))
                else:
                    ambiguities.append(AmbiguityDetail(field="", message=str(amb)))

            return NLInterpretationResponse(
                success=False,
                draft=None,
                missing_fields=missing_fields,
                ambiguities=ambiguities,
                error=error_code,
                error_code=error_code,
            )

    def _build_prompt(self, user_text: str) -> str:
        """Build the prompt for the LLM."""
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")

        examples_text = ""
        for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
            examples_text += f"\nExample {i}:\nInput: {ex['input']}\nOutput: {ex['output']}\n"

        return PROMPT_TEMPLATE.substitute(
            system_prompt=SYSTEM_PROMPT,
            examples=examples_text,
            current_date=current_date,
            user_text=user_text,
        )

    def _get_current_date(self) -> str:
        """Get current date in ISO format."""
        return datetime.now(UTC).strftime("%Y-%m-%d")


async def interpret_natural_language(
    request: NLInterpretationRequest,
    llm_adapter: LLMAdapter | None = None,
) -> NLInterpretationResponse:
    """
    Convenience function to interpret a natural language request.

    Args:
        request: The interpretation request.
        llm_adapter: Optional custom LLM adapter.

    Returns:
        NLInterpretationResponse with interpretation result.
    """
    service = NLInterpreterService(llm_adapter)
    return await service.interpret(request)
