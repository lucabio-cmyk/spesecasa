from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/spese"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    agent_max_tokens: int = 4096
    agent_max_tool_iterations: int = 12

    # Auth
    jwt_secret: str = "cambia-questa-stringa"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # Storage
    storage_backend: str = "local"
    storage_dir: str = "/data/documents"

    # Semantic search (optional)
    enable_semantic_search: bool = False
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024
    voyage_api_key: str = ""

    # App
    app_env: str = "development"
    cors_origins: str = "*"

    @property
    def async_database_url(self) -> str:
        """Railway fornisce postgresql://; lo forziamo al driver asyncpg."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
