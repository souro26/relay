"""OpenAI LLM adapter implementation."""

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


class OpenAIAdapter(LLMAdapter):
    """OpenAI API adapter with structured output support."""

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
        Initialize the OpenAI adapter.

        Args:
            api_key: OpenAI API key. Falls back to settings.llm_api_key.
            base_url: Custom base URL (e.g., for Azure OpenAI). Falls back to settings.llm_base_url.
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
                "OpenAI API key not configured. Set LLM_API_KEY environment variable.",
                "openai",
            )
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or settings.llm_base_url,
            timeout=timeout or settings.llm_timeout,
        )
        if model:
            self._model = model
        elif settings.llm_model and not settings.llm_model.startswith("nvidia/"):
            self._model = settings.llm_model
        else:
            self._model = "gpt-4o-mini"
        self._timeout = timeout or settings.llm_timeout
        self._max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        self._retry_backoff_base = (
            retry_backoff_base
            if retry_backoff_base is not None
            else settings.llm_retry_backoff_base
        )

    @property
    def provider_name(self) -> str:
        return "openai"

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
                    "Calling OpenAI API",
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
                    f"OpenAI request timed out after {self._timeout}s",
                    "openai",
                    e,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    last_exception = LLMProviderError(
                        "OpenAI rate limit exceeded",
                        "openai",
                        status_code=429,
                        original_error=e,
                    )
                elif 500 <= e.response.status_code < 600:
                    last_exception = LLMProviderError(
                        f"OpenAI server error: {e.response.status_code}",
                        "openai",
                        status_code=e.response.status_code,
                        original_error=e,
                    )
                else:
                    last_exception = LLMProviderError(
                        f"OpenAI API error: {e.response.status_code}",
                        "openai",
                        status_code=e.response.status_code,
                        original_error=e,
                    )
            except httpx.RequestError as e:
                last_exception = LLMProviderError(
                    f"Failed to connect to OpenAI: {e}",
                    "openai",
                    original_error=e,
                )
            except Exception as e:
                last_exception = LLMProviderError(
                    f"Unexpected OpenAI error: {e}",
                    "openai",
                    original_error=e,
                )
            else:
                latency_ms = (time.monotonic() - start_time) * 1000

                if not response.choices or not response.choices[0].message.content:
                    raise LLMOutputParseError(
                        "OpenAI returned empty response",
                        "openai",
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
                    provider="openai",
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
                        "provider": "openai",
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
                provider="openai",
                attempt=attempt + 1,
            )
            raise last_exception

        # Should not reach here
        raise last_exception

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()


def get_llm_adapter() -> "LLMAdapter":
    """
    Factory function to create an LLM adapter based on settings.

    Returns:
        An LLMAdapter instance based on settings.llm_provider.

    Raises:
        LLMConfigurationError: If the provider is not supported or not configured.
    """
    provider = settings.llm_provider.lower()

    if provider == "nvidia":
        if not settings.llm_api_key:
            raise LLMConfigurationError(
                "LLM_API_KEY environment variable not set. "
                "Configure LLM_API_KEY to use natural language interpretation with NVIDIA NIM.",
                "nvidia",
            )
        from relay.adapters.llm.nvidia import NVIDIAAdapter

        return NVIDIAAdapter()

    if provider == "openai":
        if not settings.llm_api_key:
            raise LLMConfigurationError(
                "LLM_API_KEY environment variable not set. "
                "Configure LLM_API_KEY to use natural language interpretation.",
                "openai",
            )
        return OpenAIAdapter()

    raise LLMConfigurationError(
        f"Unsupported LLM provider: {settings.llm_provider}. Supported: nvidia, openai",
        settings.llm_provider,
    )
