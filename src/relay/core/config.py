from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    database_url: str
    log_level: str = "INFO"
    order_service_url: AnyHttpUrl = "http://localhost:8001"
    order_service_timeout: float = 10.0

    # LLM Configuration
    llm_provider: str = "nvidia"
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_timeout: float = 30.0

    # LLM Cost Controls & Pricing (USD per 1,000,000 tokens)
    llm_max_input_chars: int = 2000
    llm_max_output_tokens: int = 500
    llm_max_retries: int = 1
    llm_retry_backoff_base: float = 1.0
    llm_input_cost_per_million: float = 0.50
    llm_output_cost_per_million: float = 1.50

    # Demo Access Control (for expensive NL endpoint)
    demo_api_key: str | None = None

    # Rate limiting
    rate_limit_per_minute: int = 10

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper

    @field_validator("demo_api_key", "llm_api_key", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: str | None) -> str | None:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        allowed = {"nvidia", "openai"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"llm_provider must be one of {allowed}")
        return v_lower

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        # Allow SQLite for testing, PostgreSQL for production
        # Support both postgresql:// and postgresql+psycopg:// (psycopg 3 driver)
        if (
            v.startswith("sqlite://")
            or v.startswith("postgresql://")
            or v.startswith("postgres://")
            or v.startswith("postgresql+psycopg://")
        ):
            return v
        raise ValueError("database_url must be a SQLite or PostgreSQL URL")

    def estimate_llm_cost(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> float | None:
        """Calculate estimated LLM cost based on instance configuration."""
        return estimate_llm_cost(
            prompt_tokens,
            completion_tokens,
            self.llm_input_cost_per_million,
            self.llm_output_cost_per_million,
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    global _settings, settings
    _settings = Settings()
    settings = _settings
    return _settings


settings = get_settings()


def estimate_llm_cost(
    prompt_tokens: int | None,
    completion_tokens: int | None,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
) -> float | None:
    """Calculate estimated LLM cost in USD based on configurable token rates.

    Returns None if neither prompt nor completion tokens are provided.
    """
    if prompt_tokens is None and completion_tokens is None:
        return None

    in_rate = (
        input_cost_per_million
        if input_cost_per_million is not None
        else settings.llm_input_cost_per_million
    )
    out_rate = (
        output_cost_per_million
        if output_cost_per_million is not None
        else settings.llm_output_cost_per_million
    )

    cost = ((prompt_tokens or 0) / 1_000_000.0) * in_rate + (
        (completion_tokens or 0) / 1_000_000.0
    ) * out_rate
    return round(cost, 6)

