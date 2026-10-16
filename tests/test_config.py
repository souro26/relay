import pytest
from pydantic import ValidationError

from relay.core.config import Settings


class TestSettings:
    def test_settings_load_from_env(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        settings = Settings()
        assert settings.environment == "production"
        assert str(settings.database_url) == "postgresql://user:pass@host:5432/db"
        assert settings.log_level == "DEBUG"

    def test_settings_defaults(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")

        settings = Settings()
        assert settings.environment == "development"
        assert settings.log_level == "INFO"

    def test_settings_invalid_environment(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
        monkeypatch.setenv("ENVIRONMENT", "invalid")

        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "environment" in str(exc_info.value)

    def test_settings_invalid_log_level(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "log_level" in str(exc_info.value)

    def test_settings_missing_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from pydantic_settings import SettingsConfigDict

        from relay.core.config import Settings

        # Create a new Settings class that doesn't read from .env
        class TestSettings(Settings):
            model_config = SettingsConfigDict(
                env_file=None,
                env_file_encoding="utf-8",
                case_sensitive=False,
                extra="ignore",
            )

        with pytest.raises(ValidationError) as exc_info:
            TestSettings()
        assert "database_url" in str(exc_info.value)

    def test_database_url_accepted_postgresql(self, monkeypatch):
        """Test that standard postgresql:// URLs are accepted."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
        settings = Settings()
        assert str(settings.database_url) == "postgresql://user:pass@host:5432/db"

    def test_database_url_accepted_postgres(self, monkeypatch):
        """Test that postgres:// URLs are accepted."""
        monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@host:5432/db")
        settings = Settings()
        assert str(settings.database_url) == "postgres://user:pass@host:5432/db"

    def test_database_url_accepted_postgresql_psycopg(self, monkeypatch):
        """Test that postgresql+psycopg:// URLs are accepted (psycopg 3 driver)."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")
        settings = Settings()
        assert str(settings.database_url) == "postgresql+psycopg://user:pass@host:5432/db"

    def test_database_url_accepted_sqlite(self, monkeypatch):
        """Test that sqlite:// URLs are accepted for testing."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
        settings = Settings()
        assert str(settings.database_url) == "sqlite:///./test.db"

    def test_database_url_accepted_sqlite_memory(self, monkeypatch):
        """Test that sqlite:///:memory: URLs are accepted for testing."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        settings = Settings()
        assert str(settings.database_url) == "sqlite:///:memory:"

    def test_database_url_rejected_mysql(self, monkeypatch):
        """Test that mysql:// URLs are rejected."""
        monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@host:3306/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "database_url" in str(exc_info.value)

    def test_database_url_rejected_mongodb(self, monkeypatch):
        """Test that mongodb:// URLs are rejected."""
        monkeypatch.setenv("DATABASE_URL", "mongodb://user:pass@host:27017/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "database_url" in str(exc_info.value)

    def test_database_url_rejected_invalid_scheme(self, monkeypatch):
        """Test that invalid URL schemes are rejected."""
        monkeypatch.setenv("DATABASE_URL", "invalid://user:pass@host/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "database_url" in str(exc_info.value)
