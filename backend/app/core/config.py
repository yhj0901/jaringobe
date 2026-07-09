from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수 기반 설정. .env 자동 로드. 시크릿은 .env 로만 관리(하드코딩 금지)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL (async, asyncpg)
    database_url: str = "postgresql+asyncpg://jaringobe:jaringobe@localhost:5432/jaringobe"

    # LLM (Claude) — 모델/프롬프트는 설계 단계 확정
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    # 인증 — JWT + OAuth state 서명 (.env: JWT_SECRET / JWT_ALG)
    jwt_secret: str = "dev-only-jwt-secret-do-not-use-in-prod"
    jwt_alg: str = "HS256"
    access_token_expire_minutes: int = 30  # security-design.md: Access 30분
    refresh_token_expire_days: int = 14  # security-design.md: Refresh 14일
    oauth_state_expire_minutes: int = 10  # security-design.md: state 10분

    # 소셜 로그인 provider 자격증명 (.env 전용 — 하드코딩 금지)
    kakao_client_id: str = ""
    kakao_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""

    # 프론트엔드 오리진 — Origin 검증 + OAuth 복귀 리다이렉트 베이스
    frontend_origin: str = "http://localhost:3000"

    # 쿠키 Secure 플래그 — 로컬 http 개발에서는 false, 배포(https) 시 true
    cookie_secure: bool = False

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
