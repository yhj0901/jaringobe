FROM python:3.12-slim

WORKDIR /app

# uv 설치 (하네스 지정 패키지 관리자)
RUN pip install --no-cache-dir uv

# 의존성 + 앱 설치 (hatchling 패키지 빌드)
COPY pyproject.toml ./
COPY app ./app
RUN uv pip install --system .

# 마이그레이션 실행용 (컨테이너 내 alembic upgrade head)
COPY alembic.ini ./
COPY alembic ./alembic

# 진입점 — DB 대기 → alembic upgrade head → uvicorn($PORT)
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
