#!/usr/bin/env bash
# DB 전체를 파일로 덤프한다 (서버 이관·백업용).
#
#   ./scripts/db-dump.sh [출력파일]
#
# 기본 출력: backups/jaringobe_YYYYMMDD_HHMMSS.dump (custom 포맷, pg_restore 용)
# 대상 컨테이너는 COMPOSE_FILE 로 바꿀 수 있다 (기본: docker-compose.yml).
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
[ -f .env ] && set -a && . ./.env && set +a

PGUSER="${POSTGRES_USER:-jaringobe}"
PGDB="${POSTGRES_DB:-jaringobe}"
OUT="${1:-backups/jaringobe_$(date +%Y%m%d_%H%M%S).dump}"

mkdir -p "$(dirname "$OUT")"
echo "[dump] $PGDB → $OUT"
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$PGUSER" -d "$PGDB" -Fc > "$OUT"
echo "[dump] 완료: $OUT ($(du -h "$OUT" | cut -f1))"
