from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import ApiError, api_error_handler, error_body, validation_error_handler
from app.core.ratelimit import auth_ip_limiter

app = FastAPI(
    title="JARINGOBE API",
    description="예산 안에서 식단 자동 생성 · 식재료 0 · 자동 주문",
    version="0.1.0",
)

# CORS 미허용(기본 차단) — 프론트는 Next.js rewrites 프록시로 동일 오리진 호출 (security-design.md §3)

app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def verify_origin(request: Request, call_next) -> Response:
    """상태 변경 메서드의 Origin 헤더 검증 — CSRF 이중 방어 (CWE-352).

    Origin 이 존재하는데 FRONTEND_ORIGIN 과 불일치하면 403 FORBIDDEN_ORIGIN.
    (비브라우저 클라이언트는 Origin 미전송 — SameSite=Lax 가 1차 방어)
    """
    if request.method in _STATE_CHANGING_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin != get_settings().frontend_origin:
            return JSONResponse(
                status_code=403,
                content=error_body("FORBIDDEN_ORIGIN", "Origin header mismatch"),
            )
    return await call_next(request)


@app.middleware("http")
async def rate_limit_auth(request: Request, call_next) -> Response:
    """/api/v1/auth/* IP 기준 10회/분 (CWE-307)."""
    if request.url.path.startswith("/api/v1/auth/"):
        client_ip = request.client.host if request.client else "unknown"
        if not auth_ip_limiter.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content=error_body("RATE_LIMITED", "Too many auth requests"),
            )
    return await call_next(request)


app.include_router(api_router)


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
