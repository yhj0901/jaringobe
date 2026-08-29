from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py 기준 경로 — 실행 CWD 와 무관하게 .env 를 찾는다.
_BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend
_REPO_ROOT = _BACKEND_DIR.parent  # 저장소 루트 (컨테이너에서는 존재하지 않을 수 있음)


class Settings(BaseSettings):
    """환경변수 기반 설정. .env 자동 로드. 시크릿은 .env 로만 관리(하드코딩 금지).

    .env 탐색 순서: 저장소 루트 → backend/ (뒤쪽이 우선).
    실제 OS 환경변수가 항상 최우선이므로 컨테이너/PaaS 배포에는 영향이 없다.
    """

    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL (async, asyncpg)
    database_url: str = "postgresql+asyncpg://jaringobe:jaringobe@localhost:5432/jaringobe"

    # LLM (Claude) — 모델/프롬프트는 설계 단계 확정
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    # 마트 연동 — 네이버 쇼핑 검색 API (.env 전용, 하드코딩 금지)
    naver_client_id: str = ""
    naver_client_secret: str = ""

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
