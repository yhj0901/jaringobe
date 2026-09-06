# 백엔드 이관/실행 가이드 (어느 호스트에서든)

> 백엔드는 **Docker 이미지 1개 + PostgreSQL 1개 + `.env` 1개**로 완결된다.
> 상태는 전부 DB 에 있고, 코드에는 호스트 고정값이 없다. 따라서 로컬 → VPS → 클라우드 이관이 동일 절차다.

## 1. 구성 요소

| 파일 | 용도 |
|------|------|
| `backend/Dockerfile` | 백엔드 이미지 (python 3.12-slim + uv) |
| `backend/docker-entrypoint.sh` | 기동 시 **DB 대기 → `alembic upgrade head` → uvicorn(`$PORT`)** |
| `docker-compose.yml` | 로컬 개발 (db + backend) |
| `docker/docker-compose.server.yml` | 이관/배포 서버 (db + backend + Caddy 자동 TLS) |
| `docker/Caddyfile` | `API_DOMAIN` 주입형 리버스 프록시 |
| `docker/initdb/01-create-test-db.sh` | postgres 최초 초기화 시 테스트 DB 자동 생성 |
| `.env` | 백엔드·compose 공통 설정 (**커밋 금지**, `.env.example` 참고) |
| `frontend/.env.local` | 프론트 전용 `BACKEND_URL` — Next.js 는 `frontend/` 기준으로 env 를 읽는다 (**커밋 금지**) |
| `scripts/db-dump.sh` · `scripts/db-restore.sh` | 데이터 이관용 백업/복원 |

**핵심 설계**
- 백엔드 컨테이너가 스스로 마이그레이션을 적용한다 → 새 호스트에서 별도 절차 불필요 (`RUN_MIGRATIONS=false` 로 비활성화 가능)
- `$PORT` 를 주입하는 PaaS(Railway/Fly/Render/Cloud Run)도 그대로 지원
- 설정은 **OS 환경변수 > `backend/.env` > 루트 `.env`** 우선순위. 컨테이너에서는 환경변수만으로 완전 구동된다
- DB 포트·백엔드 포트는 `POSTGRES_PORT` / `BACKEND_PORT` 로 조정 (한 머신에서 다른 프로젝트와 충돌 시)

---

## 2. 로컬 실행

```bash
cp .env.example .env
# JWT_SECRET 채우기:  openssl rand -hex 32
# 포트가 이미 쓰이면 POSTGRES_PORT / BACKEND_PORT 변경 후 DATABASE_URL·TEST_DATABASE_URL 포트도 맞출 것

docker compose up -d --build
curl http://localhost:${BACKEND_PORT:-8000}/health     # {"status":"ok","db":true,...}
```

컨테이너 로그에서 `alembic upgrade head` 가 자동 실행된 것을 확인할 수 있다.

```bash
docker compose logs -f backend
docker compose down          # 중지 (데이터 유지)
docker compose down -v       # 중지 + DB 볼륨 삭제
```

### 코드 수정하며 개발 (핫 리로드)
DB 만 컨테이너로 띄우고 백엔드는 호스트에서 실행한다. 루트 `.env` 는 실행 위치와 무관하게 자동 로드된다.

```bash
docker compose up -d db
cd backend
uv sync --all-groups
uv run uvicorn app.main:app --reload --port 8000
```

### 테스트
```bash
cd backend && uv run pytest --cov=app     # 커버리지 90% 이상 유지 (커밋 기준)
```
테스트는 `TEST_DATABASE_URL` DB 를 쓰고 매 테스트마다 `public` 스키마를 재생성한다.
외부 API(Claude·네이버) 키는 conftest 가 강제로 비우므로 `.env` 의 실 키가 테스트로 새지 않는다.

---

## 3. 다른 서버로 이관

### 3-1. 새 호스트 준비
Docker + Docker Compose 만 있으면 된다.

```bash
git clone <저장소> jaringobe && cd jaringobe
cp .env.example .env && vi .env
```

`.env` 에서 반드시 바꿀 값:

| 키 | 값 |
|----|-----|
| `POSTGRES_PASSWORD` | 강한 랜덤 문자열 |
| `JWT_SECRET` | `openssl rand -hex 32` (**바꾸면 기존 세션 전부 만료**) |
| `FRONTEND_ORIGIN` | 프론트 실도메인 (예: `https://jaringobe.vercel.app`) |
| `COOKIE_SECURE` | https 서비스면 **반드시 `true`** |
| `API_DOMAIN` | 백엔드 도메인 (예: `api.example.com`). 비우면 `:80` HTTP |
| `KAKAO_*` / `GOOGLE_*` | 소셜 로그인 키 (콜백 URL 재등록 필요) |
| `ANTHROPIC_API_KEY` | 비우면 AI 식단이 mock 모드 |

### 3-2. 기동
```bash
docker compose -f docker/docker-compose.server.yml --env-file .env up -d --build
docker compose -f docker/docker-compose.server.yml logs -f backend   # 마이그레이션 자동 적용 확인
```

- `API_DOMAIN` 을 지정했다면 Caddy 가 Let's Encrypt 인증서를 자동 발급한다 → **80/443 인바운드 개방 필수**, DNS A 레코드가 서버 IP 를 가리켜야 한다
- db·backend 는 `127.0.0.1` 에만 바인딩되어 공인망에 직접 노출되지 않는다. 외부 진입점은 Caddy 뿐이다
- 팀원 DB 접속은 SSH 터널로만: `ssh -L 15432:localhost:5432 <user>@<host>` → `localhost:15432`

### 3-3. 데이터 이관 (기존 DB 를 옮길 때)
```bash
# 기존 호스트에서
COMPOSE_FILE=docker/docker-compose.server.yml ./scripts/db-dump.sh
scp backups/jaringobe_*.dump <새호스트>:~/jaringobe/backups/

# 새 호스트에서 (스택 기동 후)
COMPOSE_FILE=docker/docker-compose.server.yml ./scripts/db-restore.sh backups/jaringobe_YYYYMMDD_HHMMSS.dump
```
> 복원은 `--clean` 으로 기존 객체를 삭제한 뒤 수행한다. 대상 DB 의 데이터는 사라지므로 순서를 지킬 것.

### 3-4. 이관 후 체크리스트
- [ ] `curl https://<API_DOMAIN>/health` → `{"status":"ok","db":true}`
- [ ] 카카오/구글 개발자 콘솔에 새 콜백 URL 등록 (`<FRONTEND_ORIGIN>/api/v1/auth/{provider}/callback`)
- [ ] 프론트(Vercel) 환경변수 `BACKEND_URL` 을 새 백엔드 주소로 변경 후 재배포
- [ ] `COOKIE_SECURE=true` · `FRONTEND_ORIGIN` 실도메인 확인 (버그리포트 R-1)
- [ ] 이전 호스트 종료 전 최종 덤프 1회 확보

---

## 4. 관리형 PaaS 로 올릴 때

`backend/Dockerfile` 을 그대로 쓰고 관리형 PostgreSQL 을 붙인다.

1. 빌드 컨텍스트 = `backend/`, 포트는 플랫폼이 주입하는 `$PORT` 를 entrypoint 가 그대로 사용
2. 환경변수로 `DATABASE_URL` 주입 — **드라이버는 반드시 `postgresql+asyncpg://`**
   (관리형 DB 가 주는 `postgres://` / `postgresql://` 는 동기 드라이버로 해석되어 기동 실패)
3. TLS·도메인은 플랫폼이 처리하므로 Caddy 불필요
4. 마이그레이션은 첫 기동 시 entrypoint 가 자동 적용. 인스턴스를 여러 개 띄운다면 한 곳에서만 돌도록
   `RUN_MIGRATIONS=false` + 별도 release 단계에서 `alembic upgrade head` 실행 권장

**멀티 인스턴스 주의**: rate limit 이 아직 인메모리라 인스턴스별로 따로 센다(버그리포트 R-2). 수평 확장 시 Redis 로 교체 필요.

---

## 5. 문제 해결

| 증상 | 원인·조치 |
|------|-----------|
| `/health` 의 `db:false` | `DATABASE_URL` 호스트/포트 오류. 컨테이너 내부는 `db:5432`, 호스트 실행은 `localhost:${POSTGRES_PORT}` |
| 포트 충돌 (`address already in use`) | `.env` 의 `POSTGRES_PORT`/`BACKEND_PORT` 변경 → `DATABASE_URL`·`TEST_DATABASE_URL` 포트도 함께 수정 |
| `[entrypoint] DB 연결 실패` | db 가 아직 준비 안 됨. `DB_WAIT_TIMEOUT`(기본 60초) 상향 또는 DB 상태 확인 |
| `cannot drop table ... other objects depend on it` (테스트) | 다른 브랜치 리비전의 잔여 테이블. `DROP DATABASE jaringobe_test; CREATE DATABASE jaringobe_test;` |
| 로그인 후 401 반복 | `COOKIE_SECURE`/`FRONTEND_ORIGIN` 불일치. https 서비스에서 `COOKIE_SECURE=false` 면 쿠키가 저장되지 않음 |
| `403 FORBIDDEN_ORIGIN` | 요청 `Origin` 이 `FRONTEND_ORIGIN` 과 불일치 |
| Caddy 인증서 발급 실패 | DNS A 레코드·80/443 인바운드 확인. 급하면 `API_DOMAIN` 을 비워 HTTP 로 우회 검증 |
