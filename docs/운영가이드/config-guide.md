# 환경 변수 설정 가이드 (.env)

> 템플릿: `.env.example` (커밋 대상). 실제 `.env` 는 커밋 금지. 시크릿은 여기로만 관리. 정본 코드: `backend/app/core/config.py`(pydantic Settings, OS 환경변수 > `backend/.env` > 루트 `.env`) · `backend/app/domains/cycle/policy.py`(CYCLE_* 해석). 기준 시점: v0.2.0 (2026-09-05).

## 기본·인증·외부 키

| 키 | 사용처 | 설명 | 로컬 기본 | 배포 시 |
|----|--------|------|-----------|---------|
| `POSTGRES_USER/PASSWORD/DB` | docker | postgres 초기화 | jaringobe/…/jaringobe | 강한 비밀번호 필수 |
| `POSTGRES_PORT` / `BACKEND_PORT` | docker compose | 호스트 노출 포트(다른 프로젝트와 충돌 시 변경). 컨테이너 내부 포트는 5432/8000 고정 | 5432 / 8000 | 서버 compose 는 127.0.0.1 바인딩 |
| `DATABASE_URL` | backend | asyncpg 접속 문자열. **호스트 실행용** — 포트는 `POSTGRES_PORT` 와 일치 | `…@localhost:5432/jaringobe` | compose 가 내부 `db:5432` 로 덮어씀 |
| `TEST_DATABASE_URL` | backend(pytest) | 테스트 전용 DB — 매 테스트 스키마 drop/create. **운영 DB 와 반드시 분리** | `…/jaringobe_test` | CI 전용 |
| `JWT_SECRET` | backend | JWT·OAuth state 서명 | (빈값 불가 — 생성 필요) | `openssl rand -hex 32` |
| `KAKAO_CLIENT_ID/SECRET` · `GOOGLE_CLIENT_ID/SECRET` | backend | 소셜 OAuth | 빈값(로그인 불가) | 각 콘솔 발급 + 콜백 URL 등록 |
| `FRONTEND_ORIGIN` | backend | Origin 검증(POST/PUT/PATCH/DELETE) + OAuth·앱 세션 복귀 리다이렉트 베이스 | http://localhost:3000 | **프론트 실제 도메인** (불일치 시 403/리다이렉트 오류) |
| `COOKIE_SECURE` | backend | 쿠키 Secure 플래그 | false | **true 필수** (https). 로컬 복귀 시 false 로 되돌릴 것 |
| `BACKEND_URL` | frontend (`frontend/.env.local`) | rewrites 프록시 대상 | http://localhost:8000 | 백엔드 공개 https 주소 (Vercel env) |
| `ANTHROPIC_API_KEY` / `LLM_MODEL` | backend | AI 식단. 빈값이면 `/health` 의 `llm:"mock"`, 냉장고 되먹임 힌트 미반영 | 빈값 / `claude-sonnet-5` | 실키 |
| `NAVER_CLIENT_ID/SECRET` | backend | 네이버 쇼핑 검색(주문 추정가). 빈값이면 preview 라인 `matched=false`·총액 0·`notes=[PRICE_LOOKUP_UNAVAILABLE]` (5xx 아님) | 빈값 | developers.naver.com |
| `EXPO_ACCESS_TOKEN` | backend | Expo Push API Bearer. 빈값이면 **무인증 발송 시도**(개발용) | 빈값 | expo.dev Access Token |
| `APP_SCHEME` | backend | 앱 로그인 복귀 딥링크 스킴 (`{APP_SCHEME}://auth?code=`) | `jaringobe` | 앱 `app.json` scheme 과 일치 |

## 운영 파라미터 — 식단·리마인더 (기본값 있음, `.env.example` 에는 주석)

| 키 | 기본 | 용도 |
|----|------|------|
| `MEALPLAN_GENERATION_TIMEOUT_MINUTES` | 10 | `processing` 좀비 플랜을 `failed` 로 수렴(서버 재시작 등으로 백그라운드 태스크 유실 대비) |
| `REMINDER_SCHEDULER_ENABLED` | true | 식사 리마인더 스케줄러 기동 (멀티 인스턴스 시 1대만) |
| `REMINDER_SCHEDULER_INTERVAL_SECONDS` | 30 | 폴링 주기 |

## 운영 파라미터 — 주간 자동 사이클 `CYCLE_*` (18개, 시크릿 아님, 전부 기본값 있음)

전역 정책 = 환경변수 / 사용자 정책 = `user_cycle_settings` 컬럼. 설정 테이블은 없다(관리자 인증 도입 후 승격 검토). **파싱 실패(잘못된 JSON·범위 밖 값)는 앱을 죽이지 않고 기본값 + 경고 로그 `사이클 정책 파싱 실패 — 기본값 사용 key=…`** (BUG-011 해소 전에는 이 경고도 출력되지 않으니 값 변경 후 동작을 직접 확인).

| 키 | 기본값 | 용도 | 비고 |
|----|--------|------|------|
| `CYCLE_SCHEDULER_ENABLED` | `true` | 사이클 스케줄러 기동 | **멀티 인스턴스 시 1대만 true**. HTTP 테스트·부하 회피 시 false |
| `CYCLE_SCHEDULER_INTERVAL_SECONDS` | `60` | tick 주기(초, 최소 1) | QA 실루프는 5 로 실행 |
| `CYCLE_PROFILE_WEEKLY` | `{"generateLeadDays":5,"draftLeadDays":2,"graceHours":24}` | 주 1회 프로파일: D-5 생성 / D-2 초안 / 24h 그레이스 | JSON |
| `CYCLE_PROFILE_BIWEEKLY` | `{"generateLeadDays":2,"draftLeadDays":1,"graceHours":12}` | 주 2회 프로파일 | 단계가 겹치지 않게 프로파일별 값 |
| `CYCLE_STAGE_LOCAL_HOUR` | `9` | 단계 실행·배송 예정 로컬 시각(시, 0~23) | |
| `CYCLE_JITTER_MINUTES` | `30` | 사용자별 결정적 지터 폭(분, 0 허용) | 동시 폭주로 자기 리미터를 치는 것 방지 |
| `CYCLE_ACTIVE_COMPLETION_MIN` | `1` | 활성 판정 — 지난 사이클 식사 완료 최소 건수 | |
| `CYCLE_ACTIVE_SEEN_DAYS` | `14` | 활성 판정 — 최근 접속(`users.last_seen_at`) 일수 | |
| `CYCLE_DAILY_GENERATION_LIMIT` | `200` | **전체** 일일 자동 식단 생성 상한(UTC 일). 도달 시 `deferred_quota` 익일 이월 | LLM 비용 방어선 — 임의 제거 금지 |
| `CYCLE_UNMATCHED_THRESHOLD` | `0.30` | 자동확정 미매칭 비율 임계(0~1) | 초과 → `awaiting_user/UNMATCHED_RATIO` |
| `CYCLE_DELIVERY_LEAD_DAYS` | `{"kurly":1,"coupang":1,"ssg":1,"naver":2,"walmart":2,"instacart":1}` | 스토어별 배송 리드일 → `delivery_eta` | JSON, 미정의 스토어는 아래 기본 |
| `CYCLE_DELIVERY_LEAD_DAYS_DEFAULT` | `1` | 리드일 기본값(0 허용) | |
| `CYCLE_EXPIRING_DAYS` | `{"KR":3,"US":5}` | 국가별 임박 판정 일수(프롬프트 "Use these FIRST") | US 는 주 1회 대량 배송 전제로 길게 |
| `CYCLE_FRIDGE_PROMPT_MAX_EXPIRING_LINES` | `15` | 프롬프트 임박 재고 최대 줄 | 0 허용 |
| `CYCLE_FRIDGE_PROMPT_MAX_LINES` | `25` | 프롬프트 일반 재고 최대 줄 | 합 40줄 ≈ 500토큰 |
| `CYCLE_DRAFT_RETRY_DELAYS_MINUTES` | `1,5,15` | 초안 생성 실패 백오프(분, 쉼표 구분). 횟수 초과 시 시세 없이 폴백 초안 | |
| `CYCLE_CANCEL_WINDOW_DAYS` | `7` | 확정 취소 허용 기간(`cycle_start` 기준) | 초과 409 `ORDER_CANCEL_WINDOW_CLOSED` |
| `CYCLE_DELIVERY_UNKNOWN_ATTEMPTS` | `3` | "아직 안 왔어요" 누적 → `delivery_state='unknown'`(자동 등록 중단) | |

## `config.py` 에만 있는 키 (`.env.example` 미기재 — 필요 시 OS 환경변수로)

| 키 | 기본 | 용도 |
|----|------|------|
| `JWT_ALG` | HS256 | JWT 알고리즘 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | 30 / 14 | 토큰 수명 (security-design) |
| `OAUTH_STATE_EXPIRE_MINUTES` | 10 | OAuth state 수명 |
| `APP_LOGIN_CODE_EXPIRE_SECONDS` | 60 | 앱 원타임 로그인 코드 수명 |

## 컨테이너 진입점·서버 compose 전용

| 키 | 기본 | 용도 |
|----|------|------|
| `RUN_MIGRATIONS` | true | 기동 시 `alembic upgrade head` 자동 실행 (false 면 수동 운용) |
| `DB_WAIT_TIMEOUT` | 60 | 진입점의 DB 연결 대기 상한(초) |
| `PORT` | 8000 | PaaS 가 주입하는 포트(Railway/Fly/Render/Cloud Run 대응) |
| `API_DOMAIN` | 빈값 | Caddy 자동 TLS 도메인. 비우면 :80 HTTP |

### ⚠ 서버 compose 의 환경변수 전달 범위 (인프라 후속)
`docker/docker-compose.server.yml` 은 `env_file` 을 쓰지 않고 `environment` 를 명시 열거한다(DB·JWT·FRONTEND_ORIGIN·COOKIE_SECURE·OAuth·LLM·NAVER·RUN_MIGRATIONS). 따라서 **`CYCLE_*` 18개 · `EXPO_ACCESS_TOKEN` · `APP_SCHEME` · `REMINDER_*` · `MEALPLAN_GENERATION_TIMEOUT_MINUTES` 는 서버 컨테이너에 전달되지 않고 코드 기본값으로 동작한다.** 서버에서 스케줄러 on/off 나 정책값 조정, Expo 인증 발송이 필요하면 compose 에 항목을 추가해야 한다. 로컬 `docker-compose.yml` 은 `env_file: .env` 라 전부 전달된다.

## 스케줄러 on/off 조합

| 상황 | 설정 |
|------|------|
| 로컬 개발(기본) | 둘 다 true — 기동 로그 "주간 사이클 스케줄러 시작"(로거 구성 후 표시) |
| HTTP 계약 테스트·수동 검증 | `CYCLE_SCHEDULER_ENABLED=false`(필요 시 `REMINDER_SCHEDULER_ENABLED=false`) — QA `:8011` 방식 |
| 실루프 빠른 관측 | `CYCLE_SCHEDULER_ENABLED=true CYCLE_SCHEDULER_INTERVAL_SECONDS=5` — QA `:8012` 방식 |
| 멀티 인스턴스 배포 | 스케줄러 2종 모두 **1대만 true**, 나머지 false. `uvicorn --workers` 도 1 |

- 키 추가/변경은 인프라 에이전트가 `.env.example` 과 이 문서를 함께 갱신한다
- 애플 로그인(P1) 도입 시 추가 예정: `APPLE_CLIENT_ID / APPLE_TEAM_ID / APPLE_KEY_ID / APPLE_PRIVATE_KEY_PATH`
