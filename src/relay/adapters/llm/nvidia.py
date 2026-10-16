"""NVIDIA NIM LLM adapter implementation."""

import logging
import time
from typing import Any

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from relay.adapters.llm.base import (
    LLMAdapter,
    LLMConfigurationError,
    LLMOutputParseError,
    LLMProviderError,
    LLMResponse,
    LLMTimeoutError,
    LLMUsage,
)
from relay.core.config import settings
from relay.core.logging import log_llm_call

logger = logging.getLogger(__name__)


class NVIDIAAdapter(LLMAdapter):
    """NVIDIA NIM API adapter with structured output support.

    Uses the OpenAI-compatible NVIDIA NIM API endpoint.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        retry_backoff_base: float | None = None,
    ):
        """
        Initialize the NVIDIA NIM adapter.

        Args:
            api_key: NVIDIA API key. Falls back to settings.llm_api_key.
            base_url: Custom base URL. Falls back to settings.llm_base_url or NVIDIA default.
            model: Model name. Falls back to settings.llm_model.
            timeout: Request timeout in seconds. Falls back to
                settings.llm_timeout.
            max_retries: Maximum retry attempts. Falls back to
                settings.llm_max_retries.
            retry_backoff_base: Base backoff for exponential retry. Falls back to
                settings.llm_retry_backoff_base.
        """
        api_key = api_key or settings.llm_api_key
        if not api_key:
            raise LLMConfigurationError(
                "NVIDIA API key not configured. Set LLM_API_KEY environment variable.",
                "nvidia",
            )

        # Default to NVIDIA's hosted NIM endpoint
        default_base_url = "https://integrate.api.nvidia.com/v1"

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or settings.llm_base_url or default_base_url,
            timeout=timeout or settings.llm_timeout,
        )
        self._model = model or settings.llm_model
        self._timeout = timeout or settings.llm_timeout
        self._max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        self._retry_backoff_base = (
            retry_backoff_base
            if retry_backoff_base is not None
            else settings.llm_retry_backoff_base
        )

    @property
    def provider_name(self) -> str:
        return "nvidia"

    @property
    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: dict | None = None,
    ) -> LLMResponse:
        """
        Generate a completion from the LLM with retries and usage tracking.

        Args:
            prompt: The user prompt to send to the model.
            system_prompt: Optional system prompt to prepend.
            temperature: Sampling temperature (0.0 for deterministic).
            max_tokens: Maximum tokens in response.
            response_format: Optional response format specification.

        Returns:
            LLMResponse with content and usage metadata.
        """
        messages: list[ChatCompletionMessageParam] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Cap max_tokens at configured limit
        effective_max_tokens = max_tokens
        if effective_max_tokens is not None:
            effective_max_tokens = min(effective_max_tokens, settings.llm_max_output_tokens)
        else:
            effective_max_tokens = settings.llm_max_output_tokens

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": effective_max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        last_exception: Exception | None = None
        for attempt in range(self._max_retries + 1):
            start_time = time.monotonic()
            try:
                logger.debug(
                    "Calling NVIDIA NIM API",
                    extra={
                        "model": self._model,
                        "temperature": temperature,
                        "has_response_format": response_format is not None,
                        "attempt": attempt + 1,
                        "max_tokens": effective_max_tokens,
                    },
                )
                response = await self._client.chat.completions.create(**kwargs)
            except httpx.TimeoutException as e:
                last_exception = LLMTimeoutError(
                    f"NVIDIA NIM request timed out after {self._timeout}s",
                    "nvidia",
                    e,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_exception = LLMProviderError(
                        "NVIDIA NIM rate limit exceeded",
                        "nvidia",
                        status_code=429,
                        original_error=e,
                    )
                elif 500 <= e.response.status_code < 600:
                    last_exception = LLMProviderError(
                        f"NVIDIA NIM server error: {e.response.status_code}",
                        "nvidia",
                        status_code=e.response.status_code,
                        original_error=e,
                    )
                else:
                    last_exception = LLMProviderError(
                        f"NVIDIA NIM API error: {e.response.status_code}",
                        "nvidia",
                        status_code=e.response.status_code,
                        original_error=e,
                    )
            except httpx.RequestError as e:
                last_exception = LLMProviderError(
                    f"Failed to connect to NVIDIA NIM: {e}",
                    "nvidia",
                    original_error=e,
                )
            except Exception as e:
                last_exception = LLMProviderError(
                    f"Unexpected NVIDIA NIM error: {e}",
                    "nvidia",
                    original_error=e,
                )
            else:
                latency_ms = (time.monotonic() - start_time) * 1000

                if not response.choices or not response.choices[0].message.content:
                    raise LLMOutputParseError(
                        "NVIDIA NIM returned empty response",
                        "nvidia",
                    )

                content = response.choices[0].message.content.strip()

                # Extract usage metadata if available
                usage = None
                if response.usage:
                    usage = LLMUsage(
                        prompt_tokens=response.usage.prompt_tokens,
                        completion_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                    )

                # Log the LLM call with structured data
                log_llm_call(
                    logger,
                    model=self._model,
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    duration_ms=latency_ms,
                    provider="nvidia",
                    attempt=attempt + 1,
                )

                return LLMResponse(
                    content=content,
                    usage=usage,
                    model=self._model,
                    latency_ms=latency_ms,
                )

            # Retry logic
            if attempt < self._max_retries:
                backoff = self._retry_backoff_base * (2**attempt)
                logger.warning(
                    "LLM call failed, retrying",
                    extra={
                        "provider": "nvidia",
                        "model": self._model,
                        "attempt": attempt + 1,
                        "max_retries": self._max_retries,
                        "backoff_seconds": backoff,
                        "error": str(last_exception),
                    },
                )
                await __import__("asyncio").sleep(backoff)
                continue

            # All retries exhausted
            latency_ms = (time.monotonic() - start_time) * 1000
            log_llm_call(
                logger,
                model=self._model,
                duration_ms=latency_ms,
                error=str(last_exception),
                provider="nvidia",
                attempt=attempt + 1,
            )
            raise last_exception

        # Should not reach here
        raise last_exception

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
