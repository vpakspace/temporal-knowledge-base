"""Application configuration using pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Neo4jSettings(BaseSettings):
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = "temporal_kb_2026"

    model_config = {"env_prefix": "NEO4J_"}


class OpenAISettings(BaseSettings):
    api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0

    model_config = {"env_prefix": "OPENAI_"}


class AppSettings(BaseSettings):
    log_level: str = "INFO"
    neo4j: Neo4jSettings = Neo4jSettings()
    openai: OpenAISettings = OpenAISettings()

    # API authentication (empty = auth disabled)
    api_key: str = ""

    # Temporal settings
    invalidation_similarity_threshold: float = 0.5
    default_search_limit: int = 10
    episode_batch_size: int = 50

    model_config = {"env_prefix": "APP_"}


def get_settings() -> AppSettings:
    """Create settings instance loading from environment."""
    return AppSettings()
