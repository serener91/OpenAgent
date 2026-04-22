"""Configuration for the orchestrator service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/openagent"
    echo: bool = False


class RedisSettings(BaseSettings):
    """Redis configuration."""

    url: str = "redis://localhost:6379/0"
    stream_name: str = "agent_tasks"
    consumer_group: str = "orchestrator"


class LLMSettings(BaseSettings):
    """LLM configuration."""

    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str | None = None
    organization: str | None = None


class OTelSettings(BaseSettings):
    """OpenTelemetry configuration."""

    service_name: str = "orchestrator"
    exporter_otlp_endpoint: str = "http://localhost:4317"
    exporter_otlp_insecure: bool = True


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    llm: LLMSettings = LLMSettings()
    otel: OTelSettings = OTelSettings()


settings = Settings()