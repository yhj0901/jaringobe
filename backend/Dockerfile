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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
