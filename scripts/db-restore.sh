#!/usr/bin/env bash
# 덤프 파일을 현재 DB 로 복원한다 (이관 대상 호스트에서 실행).
#
#   ./scripts/db-restore.sh backups/jaringobe_20260829_120000.dump
#
# 주의: --clean 으로 기존 객체를 삭제 후 복원한다. 대상 DB 의 데이터는 사라진다.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
[ -f .env ] && set -a && . ./.env && set +a

PGUSER="${POSTGRES_USER:-jaringobe}"
PGDB="${POSTGRES_DB:-jaringobe}"
SRC="${1:?사용법: ./scripts/db-restore.sh <덤프파일>}"
[ -f "$SRC" ] || { echo "덤프 파일 없음: $SRC" >&2; exit 1; }

echo "[restore] $SRC → $PGDB (기존 객체 삭제 후 복원)"
read -r -p "계속하려면 yes 입력: " confirm
[ "$confirm" = "yes" ] || { echo "취소됨"; exit 1; }

docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_restore -U "$PGUSER" -d "$PGDB" --clean --if-exists --no-owner < "$SRC"
echo "[restore] 완료"
