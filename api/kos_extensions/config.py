"""Cloud offering configuration.

All cloud settings are loaded from environment variables. SurrealDB is the
sole backing store — no Postgres, OpenSearch, Neo4j, or Qdrant needed.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudSettings(BaseSettings):
    """Cloud deployment settings — SurrealDB + LLM only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SurrealDB
    surrealdb_url: str = Field(
        default="ws://localhost:8001",
        description="SurrealDB WebSocket URL",
    )
    surrealdb_namespace: str = Field(default="cogmem")
    surrealdb_database: str = Field(default="kos")
    surrealdb_user: str = Field(default="root")
    surrealdb_password: str = Field(default="root")

    # LLM (via LiteLLM)
    litellm_api_base: str | None = Field(default=None)
    litellm_api_key: str | None = Field(default=None)
    litellm_default_model: str = Field(default="gpt-4o-mini")

    # Embeddings
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536)

    # API server
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    # Logging
    log_level: str = Field(default="INFO")


_settings: CloudSettings | None = None


def get_cloud_settings() -> CloudSettings:
    """Get cached cloud settings instance."""
    global _settings
    if _settings is None:
        _settings = CloudSettings()
    return _settings
