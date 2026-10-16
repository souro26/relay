"""Natural language interpretation service for order change requests."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from relay.adapters.llm import (
    LLMAdapter,
    LLMConfigurationError,
    LLMOutputParseError,
    LLMProviderError,
    LLMTimeoutError,
)
from relay.core.config import settings
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

    async def interpret(self, request: NLInterpretationRequest) -> NLInterpretationResponse:
        """
        Interpret a natural language order change request.

        Args:
            request: The natural language interpretation request.

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

        try:
            # Call LLM with structured output
            llm_response = await adapter.complete(
                prompt=prompt,
                system_prompt=None,  # Included in prompt
                temperature=0.0,
                max_tokens=settings.llm_max_output_tokens,
                response_format=get_response_schema(),
            )

            # Parse structured output
            return self._parse_response(llm_response.content)

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
            logger.warning("LLM request timed out: %s", e)
            return NLInterpretationResponse(
                success=False,
                error="Interpretation request timed out. Please try again.",
                error_code="LLM_TIMEOUT",
            )
        except LLMProviderError as e:
            logger.warning("LLM provider error: %s (status: %s)", e, e.status_code)
            if e.status_code == 429:
                error_code = "LLM_RATE_LIMIT"
                message = "LLM provider rate limit exceeded. Please try again later."
            elif e.status_code and 500 <= e.status_code < 600:
                error_code = "LLM_PROVIDER_ERROR"
                message = "LLM provider temporarily unavailable. Please try again later."
            else:
                error_code = "LLM_PROVIDER_ERROR"
                message = "LLM provider error. Please try again later."
            return NLInterpretationResponse(
                success=False,
                error=message,
                error_code=error_code,
            )
        except LLMOutputParseError as e:
            logger.warning("Failed to parse LLM output: %s", e)
            return NLInterpretationResponse(
                success=False,
                error="Failed to parse interpretation result. Please try again.",
                error_code="LLM_OUTPUT_PARSE_ERROR",
            )
        except Exception:
            logger.exception("Unexpected error during NL interpretation")
            return NLInterpretationResponse(
                success=False,
                error="Internal error during interpretation. Please try again.",
                error_code="INTERNAL_ERROR",
            )

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
