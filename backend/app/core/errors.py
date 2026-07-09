"""공통 에러 규격 — api-spec.md '에러 공통 구조'.

모든 에러 응답은 {"detail": {"code": "...", "message": "..."}} 구조를 따른다.
code 는 기계 판독용(프론트 i18n 키 매핑), message 는 개발자용 영문 설명.
"""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """도메인 서비스/라우터에서 발생시키는 규격화된 API 에러."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def error_body(code: str, message: str) -> dict:
    return {"detail": {"code": code, "message": message}}


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 — FastAPI 기본 오류 배열을 VALIDATION_ERROR 코드로 래핑 (api-spec.md)."""
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "loc": list(err.get("loc", [])),
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "errors": errors,
            }
        },
    )
