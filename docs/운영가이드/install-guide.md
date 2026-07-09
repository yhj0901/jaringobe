# 설치 가이드 (로컬 개발 환경)

## 요구사항
- Docker (postgres 16 컨테이너), Python 3.12+ + **uv**, Node.js 20+ + npm

## 1. 환경 변수
```bash
cp .env.example .env
# JWT_SECRET 채우기: openssl rand -hex 32
# 카카오/구글 OAuth 키는 각 개발자 콘솔에서 발급 (없어도 서버는 뜨고, 소셜 로그인만 불가)
```

## 2. DB
```bash
docker compose up -d db          # postgres 16 (localhost:5432, jaringobe/jaringobe 기본)
cd backend && uv run alembic upgrade head
```

## 3. 백엔드 (:8000)
```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health   # {"status":"ok","db":true,...}
```

## 4. 프론트엔드 (:3000)
```bash
cd frontend
npm install
npm run dev        # BACKEND_URL 기본 http://localhost:8000 (rewrites)
# http://localhost:3000/ko → 게스트 홈
```

## 5. 테스트
```bash
# 백엔드 (테스트 DB jaringobe_test 자동 사용 — 최초 1회 생성 필요할 수 있음)
docker exec jaringobe-db-1 psql -U jaringobe -c "CREATE DATABASE jaringobe_test" || true
cd backend && uv run pytest --cov=app

# 프론트
cd frontend && npm run test -- --coverage && npm run build
```

## OAuth 콜백 URL 등록 (소셜 로그인 로컬 테스트 시)
- 카카오 개발자 콘솔: `http://localhost:3000/api/v1/auth/kakao/callback`
- 구글 클라우드 콘솔: `http://localhost:3000/api/v1/auth/google/callback`
- (redirect_uri 는 프론트 오리진 기준 — rewrites 가 백엔드로 프록시)

## 서버 배포 (요약 — 상세 절차는 배포 인프라 태스크에서 확정 예정)
- 배포 서버에 docker compose(db+backend) 구성 + `alembic upgrade head`
- 프론트는 Vercel: **Root Directory = `frontend/`**, env `BACKEND_URL` = 백엔드 공개 https 주소
- 백엔드 `.env`: `FRONTEND_ORIGIN` = Vercel 도메인, `COOKIE_SECURE=true` **필수**
