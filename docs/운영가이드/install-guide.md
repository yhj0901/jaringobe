# 설치 가이드 (로컬 개발 환경)

> 기준 시점: v0.2.0 (2026-09-05). 백엔드를 다른 서버로 옮기거나 PaaS 에 올리는 절차는 **[backend-portable-guide.md](./backend-portable-guide.md)**, 현재 작업 상태·브랜치는 **[작업-이어받기.md](./작업-이어받기.md)** 참고.

## 요구사항
- Docker (postgres 16 컨테이너), Python 3.12+ + **uv**, Node.js 20+ + npm
- (선택) 앱 쉘 실행 시 Expo CLI — `mobile/` (Expo ~52). 웹·백엔드 개발에는 불필요

## 1. 환경 변수
```bash
cp .env.example .env
# JWT_SECRET 채우기: openssl rand -hex 32
# 카카오/구글 OAuth 키는 각 개발자 콘솔에서 발급 (없어도 서버는 뜨고, 소셜 로그인만 불가)
# ANTHROPIC_API_KEY 없으면 AI 식단 mock, NAVER_* 없으면 시세 없음(주문은 matched=false 로 동작), EXPO_ACCESS_TOKEN 없으면 무인증 발송 시도
```
루트 `.env` 하나로 docker compose 와 호스트 직접 실행(uv) 양쪽이 모두 동작한다 (`config.py` 가 저장소 루트 → `backend/` 순으로 `.env` 를 찾음).

**5432/8000 이 다른 프로젝트에 쓰이고 있다면** `.env` 의 `POSTGRES_PORT`/`BACKEND_PORT` 를 바꾸고, **`DATABASE_URL`·`TEST_DATABASE_URL` 의 포트도 같은 값으로**, `frontend/.env.local` 의 `BACKEND_URL` 도 함께 맞춘다 (예: 원 개발 머신은 5433/8001 을 썼다).

주간 사이클·리마인더 정책값(`CYCLE_*`, `REMINDER_*`)은 전부 기본값이 있으므로 로컬에서는 건드리지 않아도 된다. 상세는 [config-guide.md](./config-guide.md).

## 2. 백엔드 한 번에 띄우기 (권장)
```bash
docker compose up -d --build
curl http://localhost:${BACKEND_PORT:-8000}/health   # {"status":"ok","db":true,"llm":"mock"|"claude","detail":null}
```
- `alembic upgrade head` 는 백엔드 컨테이너 진입점(`docker-entrypoint.sh`)이 DB 대기 후 자동 실행한다 (`RUN_MIGRATIONS=false` 로 끄고 수동 운용 가능). 현재 head 는 `0012`
- 기동과 함께 **스케줄러 2개**(리마인더 30초 / 주간 사이클 60초)가 lifespan 태스크로 돈다. 로그·부하를 피하려면 `.env` 에 `CYCLE_SCHEDULER_ENABLED=false` / `REMINDER_SCHEDULER_ENABLED=false`
- 최초 초기화 시 `docker/initdb` 가 테스트 DB(`jaringobe_test`)를 자동 생성한다

## 3. 코드 고치며 개발 (핫 리로드)
DB 만 컨테이너로 띄우고 백엔드는 호스트에서 실행한다.
```bash
docker compose up -d db
cd backend
uv sync --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port ${BACKEND_PORT:-8000}
```
- **워커를 늘리지 마라** (`--workers N` 금지): 사이클 스케줄러는 단일 인스턴스 전제다. 프로세스가 2개면 식단 자동 생성이 중복 트리거될 수 있다
- 기존 데이터베이스에 0011 을 처음 적용할 때는 [db-guide](../기술문서/db-guide.md) 의 백필 검증 쿼리(재등록 후보 0건)를 확인한다

## 4. 프론트엔드 (:3000)
```bash
cd frontend
npm install
# Next.js 는 frontend/ 기준으로 env 를 읽는다 — 루트 .env 와 별도로 둘 것
echo "BACKEND_URL=http://localhost:${BACKEND_PORT:-8000}" > .env.local
npm run dev
# http://localhost:3000/ko → 게스트 홈 / 로그인 후 홈에 사이클 상태 카드·자동주문 카드, /orders, /fridge, /settings, /settings/notifications
```
로컬 스택은 외부 의존 없이 완결된다: `브라우저 → :3000 (Next.js) → rewrites → :8000 (FastAPI) → :5432 (postgres)`. 터널은 Vercel 프론트를 살릴 때만 필요하다([작업-이어받기.md](./작업-이어받기.md) 7장).

## 5. 테스트
```bash
# 백엔드 — TEST_DATABASE_URL 의 DB 사용 (매 테스트 스키마 drop/create, 운영 DB 와 분리 필수)
cd backend && uv run pytest --cov=app            # 기준선(2026-09-05 QA): 375 passed / 커버리지 94%
cd backend && uv run ruff check . && uv run mypy app

# 프론트
cd frontend && npx vitest run --coverage         # 기준선: 509 passed / 94.61%
cd frontend && npm run typecheck                 # tsc --noEmit
cd frontend && npm run build
```
- 테스트 DB 가 없다면: `docker exec jaringobe-db psql -U jaringobe -c "CREATE DATABASE jaringobe_test"`
- Node 20+ 의 실험적 Web Storage 가 jsdom 을 가려 vitest 전건이 깨지는 문제는 `frontend/vitest.setup.ts` 가 인메모리 Storage 로 교체해 해소했다. **별도 플래그(`--no-experimental-webstorage`) 불필요**
- 커버리지 90% 미만 커밋 금지 (CLAUDE.md)

### QA 하네스 (선택 — 루프 실증)
`docs/테스트/harness/` 의 가상 시계 하네스로 4사이클 루프를 직접 돌려볼 수 있다(전용 DB 필요, 실키 불필요). 절차는 `docs/테스트/harness/README.md`. `http_tests.py` 실행 시 `QA_DB` 를 `DATABASE_URL` 의 DB 명과 맞출 것.

## OAuth 콜백 URL 등록 (소셜 로그인 로컬 테스트 시)
- 카카오 개발자 콘솔: `http://localhost:3000/api/v1/auth/kakao/callback`
- 구글 클라우드 콘솔: `http://localhost:3000/api/v1/auth/google/callback`
- (redirect_uri 는 프론트 오리진 기준 — rewrites 가 백엔드로 프록시)
- 앱 웹뷰 로그인은 같은 콜백을 쓰고 `client=app` 으로 `{APP_SCHEME}://auth?code=` 딥링크로 복귀한다

## 앱 쉘 (선택)
```bash
cd mobile && npm install && npx expo start
```
웹뷰가 프론트 오리진을 감싼다. UA 접미사 ` JaringobeApp/{v} ({ios|android})` + `window.ReactNativeWebView` 로 웹이 앱을 감지한다. 푸시 실발송에는 `EXPO_ACCESS_TOKEN` 과 실기기가 필요하다(QA BLOCKED).

## 서버 배포 (요약)
- `docker compose -f docker/docker-compose.server.yml --env-file .env up -d --build` (db 127.0.0.1 바인딩 + backend + Caddy 자동 TLS)
- 프론트는 Vercel: **Root Directory = `frontend/`**, env `BACKEND_URL` = 백엔드 공개 https 주소
- 백엔드 `.env`: `FRONTEND_ORIGIN` = Vercel 도메인, `COOKIE_SECURE=true` **필수**, `API_DOMAIN` = 백엔드 도메인
- **주의**: 서버 compose 는 `environment` 를 명시 열거하므로 `CYCLE_*`·`EXPO_ACCESS_TOKEN`·`APP_SCHEME`·`REMINDER_*` 가 컨테이너에 전달되지 않는다(코드 기본값으로 동작). 서버에서 스케줄러를 끄거나 정책값을 바꾸려면 compose 갱신이 필요하다(인프라 후속, [config-guide.md](./config-guide.md))
- 운영 배포 전 필수: 앱 로거 구성(BUG-011), `COOKIE_SECURE`/`FRONTEND_ORIGIN`, 단일 인스턴스(또는 스케줄러 1대만 on)
- 현재 상시 백엔드 서버는 요금 문제로 내려져 있다 — 로컬 docker 가 정본. 상세·데이터 이관·PaaS 배포는 [backend-portable-guide.md](./backend-portable-guide.md)
