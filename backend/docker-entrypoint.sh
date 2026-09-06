#!/bin/sh
# 백엔드 컨테이너 진입점 — 어느 호스트에서든 동일하게 동작하도록 다음을 보장한다.
#   1) DB 가 연결 가능해질 때까지 대기 (compose healthcheck 가 없는 환경 대비)
#   2) alembic upgrade head 자동 실행 (RUN_MIGRATIONS=false 로 비활성화 가능)
#   3) $PORT 를 주입하는 PaaS(Railway/Fly/Render/Cloud Run 등) 대응
set -e

: "${RUN_MIGRATIONS:=true}"
: "${DB_WAIT_TIMEOUT:=60}"
: "${PORT:=8000}"

wait_for_db() {
  elapsed=0
  until python -c "
import asyncio, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import get_settings

async def main():
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
    finally:
        await engine.dispose()

asyncio.run(main())
" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$DB_WAIT_TIMEOUT" ]; then
      echo "[entrypoint] DB 연결 실패 — ${DB_WAIT_TIMEOUT}s 초과. DATABASE_URL 을 확인하세요." >&2
      exit 1
    fi
    echo "[entrypoint] DB 대기 중... (${elapsed}s)"
    sleep 2
    elapsed=$((elapsed + 2))
  done
}

if [ "$RUN_MIGRATIONS" = "true" ]; then
  wait_for_db
  echo "[entrypoint] alembic upgrade head"
  alembic upgrade head
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

echo "[entrypoint] uvicorn 기동 (port=${PORT})"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
