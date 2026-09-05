"""애플리케이션 로깅 설정.

도메인 모듈들이 logger.info(..., extra={...}) 로 구조화 필드를 남기지만
설정이 없으면 그 필드가 어디에도 출력되지 않는다. 운영에서 장애를 감지하려면
extra 가 실제로 보여야 하므로 JSON 한 줄 포맷으로 고정한다.

LOG_LEVEL / LOG_JSON 으로 조정한다 (기본 INFO / JSON).
로컬에서 사람이 읽기 편한 형태가 필요하면 LOG_JSON=false.
"""

import json
import logging
from datetime import UTC, datetime

# LogRecord 의 기본 속성 — 이 목록에 없는 키가 호출자가 넘긴 extra 다.
_STD = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """한 줄 JSON. extra 로 넘어온 키를 그대로 최상위에 펼친다."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STD or key.startswith("_"):
                continue
            payload[key] = value if isinstance(value, str | int | float | bool | None) else str(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_OURS = "_jaringobe_handler"

# INFO 에서 과하게 시끄럽거나 비밀이 실릴 수 있는 외부 로거
_THIRD_PARTY_QUIET = (
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "multipart",
    "watchfiles",
)


def configure_logging(level: str = "INFO", *, json_format: bool = True) -> None:
    """루트에 앱 전용 핸들러를 설치한다. uvicorn 로거도 같은 경로를 타게 한다.

    여러 번 호출해도 중복되지 않는다 — 이전에 이 함수가 설치한 핸들러만 걷어낸다.
    다른 곳이 붙인 핸들러(pytest caplog, 호스트 로깅 등)는 건드리지 않는다.
    루트 핸들러를 통째로 비우면 caplog 가 사라져 로그를 검증하는 테스트가 깨진다.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_format
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    setattr(handler, _OURS, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _OURS, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn 은 자체 핸들러를 붙인다 — 중복 출력을 막고 포맷을 통일한다.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True

    # 서드파티 라이브러리는 WARNING 이상만 남긴다.
    # httpx 는 INFO 에서 요청 URL 을 통째로 찍는데, 앱 로그인 원타임 코드처럼
    # 쿼리스트링에 실린 비밀이 그대로 로그에 남는다 (CWE-532/598).
    # 진단이 필요할 때만 LOG_LEVEL=DEBUG 로 함께 올린다.
    if root.level > logging.DEBUG:
        for name in _THIRD_PARTY_QUIET:
            logging.getLogger(name).setLevel(logging.WARNING)
