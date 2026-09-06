#!/bin/sh
# postgres 최초 초기화 시 1회 실행 — 백엔드 테스트용 DB 생성.
# (pytest 는 매 테스트마다 스키마를 drop/create 하므로 운영 DB 와 반드시 분리한다)
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	SELECT 'CREATE DATABASE ${POSTGRES_DB}_test'
	WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}_test')\gexec
SQL
