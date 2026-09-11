"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for BATNA."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Persistence & Cache
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/batna"
    redis_url: str = "redis://localhost:6379/0"

    # External APIs
    fred_api_key: str = ""
    bls_api_key: str = ""

    # LLMs
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_local_model: str = "qwen2.5:7b"
    default_hosted_model: str = "claude-3-5-sonnet-20241022"
    auditor_model: str = "claude-3-5-haiku-20241022"


settings = Settings()
