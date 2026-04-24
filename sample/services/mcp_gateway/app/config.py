"""Configuration for MCP Gateway service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    """Redis configuration."""

    url: str = "redis://localhost:6379/0"


class OTelSettings(BaseSettings):
    """OpenTelemetry configuration."""

    service_name: str = "mcp_gateway"
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

    redis: RedisSettings = RedisSettings()
    otel: OTelSettings = OTelSettings()


settings = Settings()