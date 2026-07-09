from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine

app = FastAPI(
    title="JARINGOBE API",
    description="예산 안에서 식단 자동 생성 · 식재료 0 · 자동 주문",
    version="0.1.0",
)

# 프론트(Next.js) 연동용 CORS — 개발 단계 전체 허용, 배포 시 도메인 제한
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """앱 + DB 연결 상태 확인 (인프라 부트스트랩 검증용)."""
    db_ok = False
    detail = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001 - 헬스체크는 모든 예외를 상태로 노출
        detail = str(exc)

    settings = get_settings()
    return {
        "status": "ok",
        "db": db_ok,
        "llm": "claude" if settings.llm_enabled else "mock",
        "detail": detail,
    }
