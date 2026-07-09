from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정. .env 자동 로드. 시크릿은 .env 로만 관리(하드코딩 금지)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL (async, asyncpg)
    database_url: str = (
        "postgresql+asyncpg://jaringobe:jaringobe@localhost:5432/jaringobe"
    )

    # LLM (Claude) — 모델/프롬프트는 설계 단계 확정
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
