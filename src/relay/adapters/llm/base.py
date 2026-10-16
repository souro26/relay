"""Base LLM adapter interface for provider-independent LLM integration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMUsage:
    """Token usage metadata from LLM provider."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class LLMResponse:
    """LLM completion response with usage metadata."""

    content: str
    usage: LLMUsage | None = None
    model: str | None = None
    latency_ms: float | None = None


class LLMAdapter(ABC):
    """Abstract base class for LLM provider adapters."""

    @abstractmethod
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
        Generate a completion from the LLM.

        Args:
            prompt: The user prompt to send to the model.
            system_prompt: Optional system prompt to prepend.
            temperature: Sampling temperature (0.0 for deterministic).
            max_tokens: Maximum tokens in response.
            response_format: Optional response format specification (e.g., JSON schema).

        Returns:
            LLMResponse with content and usage metadata.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close any underlying connections."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'openai')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name (e.g., 'gpt-4o-mini')."""
        pass


class LLMError(Exception):
    """Base exception for LLM adapter errors."""

    def __init__(self, message: str, provider: str, original_error: Exception | None = None):
        self.provider = provider
        self.original_error = original_error
        super().__init__(message)


class LLMTimeoutError(LLMError):
    """Raised when the LLM request times out."""

    pass


class LLMProviderError(LLMError):
    """Raised when the LLM provider returns an error (rate limit, outage, etc.)."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int | None = None,
        original_error: Exception | None = None,
    ):
        self.status_code = status_code
        super().__init__(message, provider, original_error)


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is invalid or missing."""

    pass


class LLMOutputParseError(LLMError):
    """Raised when the LLM output cannot be parsed."""

    pass
