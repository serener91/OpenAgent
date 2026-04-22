"""Configuration for agent services."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    """Redis configuration."""

    url: str = "redis://localhost:6379/0"
    stream_name: str = "agent_tasks"
    consumer_group: str = "agents"
    consumer_name: str = "consumer"


class OTelSettings(BaseSettings):
    """OpenTelemetry configuration."""

    service_name: str = "agent"
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
    agent_type: str = "base"

    redis: RedisSettings = RedisSettings()
    otel: OTelSettings = OTelSettings()


settings = Settings()