# 설치 가이드 (로컬 개발 환경)

> 백엔드를 다른 서버로 옮기거나 PaaS 에 올리는 절차는 **[backend-portable-guide.md](./backend-portable-guide.md)** 참고.

## 요구사항
- Docker (postgres 16 컨테이너), Python 3.12+ + **uv**, Node.js 20+ + npm

## 1. 환경 변수
```bash
cp .env.example .env
# JWT_SECRET 채우기: openssl rand -hex 32
# 카카오/구글 OAuth 키는 각 개발자 콘솔에서 발급 (없어도 서버는 뜨고, 소셜 로그인만 불가)
```
루트 `.env` 하나로 docker compose 와 호스트 직접 실행(uv) 양쪽이 모두 동작한다.
**5432/8000 이 다른 프로젝트에 쓰이고 있다면** `.env` 의 `POSTGRES_PORT`/`BACKEND_PORT` 를 바꾸고,
`DATABASE_URL`·`TEST_DATABASE_URL` 의 포트도 같은 값으로 맞춘다.

## 2. 백엔드 한 번에 띄우기 (권장)
```bash
docker compose up -d --build
curl http://localhost:${BACKEND_PORT:-8000}/health   # {"status":"ok","db":true,...}
```
`alembic upgrade head` 는 백엔드 컨테이너 진입점이 기동 시 자동 실행한다.

## 3. 코드 고치며 개발 (핫 리로드)
DB 만 컨테이너로 띄우고 백엔드는 호스트에서 실행한다.
```bash
docker compose up -d db
cd backend
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

## 4. 프론트엔드 (:3000)
```bash
cd frontend
npm install
# Next.js 는 frontend/ 기준으로 env 를 읽는다 — 루트 .env 와 별도로 둘 것
echo "BACKEND_URL=http://localhost:${BACKEND_PORT:-8000}" > .env.local
npm run dev
# http://localhost:3000/ko → 게스트 홈
```

## 5. 테스트
```bash
# 백엔드 — TEST_DATABASE_URL 의 DB 사용 (postgres 최초 초기화 시 자동 생성됨)
cd backend && uv run pytest --cov=app

# 프론트
cd frontend && npm run test -- --coverage && npm run build
```
테스트 DB 가 없다면:
```bash
docker exec jaringobe-db psql -U jaringobe -c "CREATE DATABASE jaringobe_test"
```

## OAuth 콜백 URL 등록 (소셜 로그인 로컬 테스트 시)
- 카카오 개발자 콘솔: `http://localhost:3000/api/v1/auth/kakao/callback`
- 구글 클라우드 콘솔: `http://localhost:3000/api/v1/auth/google/callback`
- (redirect_uri 는 프론트 오리진 기준 — rewrites 가 백엔드로 프록시)

## 서버 배포 (요약)
- `docker compose -f docker/docker-compose.server.yml --env-file .env up -d --build` (db + backend + Caddy 자동 TLS)
- 프론트는 Vercel: **Root Directory = `frontend/`**, env `BACKEND_URL` = 백엔드 공개 https 주소
- 백엔드 `.env`: `FRONTEND_ORIGIN` = Vercel 도메인, `COOKIE_SECURE=true` **필수**, `API_DOMAIN` = 백엔드 도메인
- 상세 절차·데이터 이관·PaaS 배포는 [backend-portable-guide.md](./backend-portable-guide.md)
