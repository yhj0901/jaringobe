# 장애 대응 가이드 (troubleshoot)

> v0.2.0 범위(자동주문·앱 웹뷰·푸시·주간 자동 사이클) 기준. 증상 → 원인 → 조치. **아래 항목은 전부 개발·QA 중 실제로 겪은 문제다** (출처: `docs/테스트/*.md`, `docs/status/*.json`, `docs/운영가이드/작업-이어받기.md`).

## 설치·환경

| 증상 | 유력 원인 | 조치 |
|------|-----------|------|
| **프론트 vitest 전건 FAIL** — `window.localStorage.clear is not a function` | Node 20+(Node 25 에서 확인)의 실험적 Web Storage 가 전역 `localStorage/sessionStorage` 를 `--localstorage-file` 없이 반쪽 객체로 노출해 jsdom 구현을 가림 | `frontend/vitest.setup.ts` 가 `clear` 가 없는 Storage 를 인메모리 구현으로 교체해 **이미 해소**. 플래그 불필요. 재발 시 setup 파일이 vitest config 에 등록돼 있는지 확인 (`--no-experimental-webstorage` 로도 회피 가능하지만 환경마다 맞춰야 해 채택 안 함) |
| `docker compose up` 이 포트 바인딩 실패 / 다른 프로젝트 DB 에 붙음 | 5432/8000 을 다른 프로젝트가 점유 | `.env` 의 `POSTGRES_PORT`/`BACKEND_PORT` 변경(원 개발 머신은 5433/8001) + **`DATABASE_URL`·`TEST_DATABASE_URL` 포트 동기화** + `frontend/.env.local` 의 `BACKEND_URL` 동기화. 셋 중 하나만 바꾸면 pytest 가 다른 DB 를 지우거나 프론트가 502 |
| 호스트에서 `uv run alembic/uvicorn` 이 DB 연결 실패 | `.env` 의 `DATABASE_URL` 호스트가 옛 기본값 `db` | v0.2.0 부터 기본 호스트는 `localhost`(compose 는 내부에서 `db` 로 덮어씀). `.env` 를 `.env.example` 기준으로 갱신 |
| `/health` 에서 `"db": false` | postgres 미기동 / `DATABASE_URL` 불일치 | `docker compose up -d db`, URL·포트 확인 |
| `/health` 의 `"llm": "mock"`, 식단이 고정 레시피만 나오고 냉장고 재료가 반영 안 됨 | `ANTHROPIC_API_KEY` 빈값 → mock 모드(되먹임 힌트 무시는 알려진 한계) | 실키 입력 후 재기동. 실 LLM 되먹임 실효성은 QA BLOCKED 항목(R-8) |
| 주문 preview 가 전부 `matched=false`, 총액 0, `notes=["PRICE_LOOKUP_UNAVAILABLE"]` | `NAVER_CLIENT_ID/SECRET` 빈값 (US 사용자는 정상 동작 — 네이버 미호출) | KR 이면 키 입력. 5xx 가 아니라 정상 폴백 |
| 소셜 로그인 불가 → 로그인 필요한 기능 전체 막힘 | `KAKAO_*`/`GOOGLE_*` 빈값(옛 서버와 함께 사라짐) | 콘솔 재발급 + 콜백 URL(`{FRONTEND_ORIGIN}/api/v1/auth/{provider}/callback`) 등록 |
| 컨테이너 기동이 `[entrypoint] DB 연결 실패 — 60s 초과` 로 종료 | DB healthcheck 전 기동 / URL 오류 | `DATABASE_URL` 확인, 필요 시 `DB_WAIT_TIMEOUT` 증가 |
| `pytest` 가 운영 데이터를 지움 | `TEST_DATABASE_URL` 이 운영 DB 를 가리킴 | 반드시 별도 DB(`jaringobe_test`). conftest 는 매 테스트 스키마 drop/create |
| 문서 저장 시 `rsync … Permission denied` (옵시디언 미러) | `CLAUDE.md` 의 미러 경로(`/Users/yangheejun/...`)가 현 머신에 없음 | 미러를 보류하고 진행(2026-09-04 status 기록). 규칙 갱신은 사용자 결정 |

## 마이그레이션

| 증상 | 유력 원인 | 조치 |
|------|-----------|------|
| **0011 적용 후 냉장고 재고가 두 배** (기존 확정 주문 재료가 다시 등록됨) | 0011 의 백필 `inbound_at := confirmed_at` 누락(수정된 리비전·수동 SQL 적용 등) → 스캔 ③이 `inbound_at IS NULL` 인 옛 confirmed 를 다시 등록 | 적용 직후 `SELECT count(*) FROM orders WHERE status='confirmed' AND inbound_at IS NULL AND delivery_eta <= now();` 가 0 인지 확인. 이미 두 배가 됐다면 `fridge_items WHERE order_id=<주문>` 중 최신 등록분을 정리하고 해당 주문 `inbound_at` 을 채운다(백업 후). 정본 0011 은 백필을 포함하며 QA M-01/02 검증됨 |
| 0011 이 `duplicate confirmed orders remain after cycle backfill` 로 중단 | 같은 사용자·사이클에 confirmed 가 2건 이상인데 강등이 실패 | 0011 은 최신 1건만 남기고 `cancelled` 강등한다. 중단됐다면 `SELECT user_id, cycle_start, count(*) … HAVING count(*)>1` 로 대상 확인 후 인프라 에이전트가 처리 |
| `alembic heads` 가 2개 / 새 리비전 down_revision 충돌 | 다른 브랜치가 같은 down_revision 을 가리킴(0009/0010 리넘버 이력 있음) | `git fetch` 후 모든 원격 브랜치 `versions/` 확인, 나중 머지 쪽이 리베이스(인프라 전담) |
| downgrade 후 초안·취소 주문 이력이 사라짐 / 알림 설정이 기본값으로 | 0011·0012 downgrade 는 **파괴적** — 비확정 주문 DELETE, 신규 알림 3종 행 DELETE | 롤백 전 손실 행 수 확인·백업(db-guide). 운영 DB 에서 함부로 downgrade 금지 |
| 마이그레이션 오류 `gen_random_uuid` | pgcrypto 확장 없음(수동 생성 DB) | 권한 있는 계정으로 `alembic upgrade head`(0001 이 확장 생성) |

## 스케줄러·사이클

| 증상 | 유력 원인 | 조치 |
|------|-----------|------|
| **스케줄러가 돌긴 하는데 로그가 한 줄도 없다** ("주간 사이클 스케줄러 시작", 단계 전이 INFO 미출력) | 앱 로거 미구성 — `app.*` INFO 가 핸들러 없이 버려짐 (BUG-011, LIVE-02) | 운영 배포 전 로거 구성 필수(R-7). 그 전까지는 DB 로 관측: `user_cycle_settings.last_stage/next_run_at`, `orders.status/auto_confirm_at/inbound_at` |
| 식단이 같은 사이클에 두 번 생성됨 / LLM 비용 2배 | 인스턴스 2대 이상(또는 `uvicorn --workers N`) 이 둘 다 스캔 ① 실행 — DB 로 막을 수 없는 유일한 스캔 | `CYCLE_SCHEDULER_ENABLED=true` 는 **1대만**, 워커 1. 형상 변경 시 설계 재소집 |
| 초안 생성 실패 시 네이버가 60초마다 호출됨 (백오프 없음) | (수정 전) 실패 핸들러가 rollback 후 만료 ORM 인스턴스에 접근해 `MissingGreenlet` 로 죽음 → 백오프 저장 실패 (BUG-002) | v0.2.0 에서 수정(`bbdf58e`): 식별자를 try 이전에 보관·재조회. 재발 시 rollback 후 ORM 접근 여부를 먼저 의심(R-6) |
| **D-1 자동확정 시점에 시세 장애가 나면 매 tick(분당 1회) 네이버 재호출** | D-1 재계산 실패 시 `auto_confirm_at` 이 그대로라 다음 tick 재시도 — 기획 5-4 백오프는 초안 단계만 규정 (BUG-012, Low) | 데이터 오류 없음, 시세 복구 시 다음 tick 정상 확정. 장애가 길면 `CYCLE_SCHEDULER_ENABLED=false` 로 일시 정지. 정책 결정 대기(R-10) |
| 스케줄러가 매 tick 같은 사용자를 재시도 / `MEALPLAN_GENERATING` 409 반복 | (수정 전) 생성 중 충돌을 예외로 처리 | v0.2.0 수정(`e349ea6`): 조용히 다음 tick 대기 |
| 예산 락 사용자의 자동주문이 2주차부터 전부 `BUDGET_EXCEEDED` (한도 0) | (수정 전) `cycle_limit` 이 주간 안분액에서 월 전체 확정액을 뺌 (리뷰 P0-1) | v0.2.0 수정(`b0c447f`): 안분·확정 모두 월초~이번 사이클 종료 누적 구간. 실측 40만원 4주 160,000/109,333/104,267/63,760 |
| 정책값을 바꿨는데 반영이 안 됨 | JSON 오타·범위 밖 값 → 기본값 폴백 + 경고 로그(로거 미구성 시 경고도 안 보임) / 재기동 안 함 | `.env` 값 JSON 유효성 확인(`CYCLE_PROFILE_*`, `CYCLE_DELIVERY_LEAD_DAYS`, `CYCLE_EXPIRING_DAYS`), 재기동. 서버 compose 는 `CYCLE_*` 를 전달하지 않음(config-guide) |
| 사용자가 "곧 준비할게요"(`deferred_quota`) 만 보고 식단이 안 생김 | 일일 자동 생성 상한(`CYCLE_DAILY_GENERATION_LIMIT` 200) 도달 — 실패 아님 | 익일 동일 로컬시각 이월. 사용자 수가 늘면 상한 조정 |
| 활성 사용자인데 자동 생성이 안 됨(`skipped_dormant`) | 지난 사이클 식사 완료 0건 또는 14일 미접속. **완료 체크 없으면 의도적으로 탈락**(과소 발주 방지 안전장치) | 홈 복귀 카드(1회) → 수동 생성 후 완료 체크가 쌓이면 다음 사이클부터 자동. 신규 사용자도 첫 식단은 홈 CTA |
| 배송분이 냉장고에 안 들어옴 | `delivery_state='unknown'`("아직 안 왔어요" 3회) → 스캔 ③ 제외 | 사용자가 `/fridge` 시트에서 "받았어요"(`POST /orders/{id}/delivery {received:true}`) → 즉시 등록 |

## API·프론트

| 증상 | 유력 원인 | 조치 |
|------|-----------|------|
| 설정 몇 번 바꾼 뒤 승인/취소가 **429 RATE_LIMITED** | 액션 리미터가 `cycle/settings`·`skip`·`approve`·`cancel`·`delivery` 5 엔드포인트 **공유 버킷** 5회/분 (BUG-007) | 1분 대기. 후속 R-11 (엔드포인트별 분리) |
| `GET /orders/preview` 4회째 429 (홈 마운트마다) | 저장 초안이 없어 매번 즉석 계산(네이버+LLM) → 3회/분 | 정상 방어. 저장 초안(스케줄러 D-2 이후)이 있으면 리미터 미적용. (v0.2.0 이전 회귀로 무제한이던 시기가 있었음 — `1dad617` 수정) |
| `GET /orders/preview?refresh=true` 를 호출해도 초안이 갱신되지 않음 | v1.9 에서 `refresh` 제거(GET 부작용 금지, CWE-650) — 보내도 무시 | `POST /orders/{id}/recalculate` 사용 |
| `POST /orders/{id}/recalculate` 등 POST 만 403 `FORBIDDEN_ORIGIN` | `FRONTEND_ORIGIN` 이 실제 접속 오리진과 불일치 (GET 은 검증 대상 아님) | backend `.env` 수정 후 재시작 |
| 로컬에서 로그인 직후 쿠키가 저장되지 않음 / 401 반복 | 터널·Vercel 검증 후 `COOKIE_SECURE=true`·`FRONTEND_ORIGIN=https://jaringobe.cloud` 를 되돌리지 않음 (http 에서 Secure 쿠키 미저장) | `COOKIE_SECURE=false`, `FRONTEND_ORIGIN=http://localhost:3000` 복원 후 재기동 |
| Vercel 프론트 `/ko` 는 200 인데 API 전부 502 | `BACKEND_URL` 이 내려간 서버(`api.jaringobe.cloud`)를 가리킴 / quick tunnel 이 죽어 URL 변경(실제 두 번 발생) | 로컬 개발엔 터널 불필요. 살리려면 named tunnel(고정 주소)로 `BACKEND_URL` 한 번만 설정(작업-이어받기 7장) |
| `/orders` 가 이번 사이클 초안 대신 이전 사이클 확정 주문 화면을 보여줌 | (수정 전) `latest` 가 이전 사이클 주문이라 확정 UI 를 막음 | v0.2.0 수정(`2ff7134`): `latest.cycleStart === preview.cycleStart` 로 분기 |
| 알림 설정 토글을 빠르게 여러 번 바꾸면 마지막 값이 유실 | (수정 전) 저장 중 변경 무시 | v0.2.0 수정(`ce10a29`): 마지막 변경 큐잉 후 재전송 |
| `POST /orders/{id}/delivery` 가 `{"received":"yes"}` 에 422 | `received` 는 StrictBool (BUG-009 수정) | boolean `true/false` 만 |
| 저장 초안 조회에서 냉장고 충당분(`fromFridge`)이 0 으로 보임 | `order_items` 에 `from_fridge` 컬럼 없음 → 스냅샷 복원 시 결손 (BUG-006, 표시만. `toBuy`·합계·차감은 정확) | 리비전 0013 후속(R-9). 즉석 계산(초안 없음)은 정확 |
| 설정 카드에서 타임존을 바꿀 수 없음 | UI 미구현(표시만, BUG-010). 서버는 동작 | `PUT /cycle/settings {timezone}` 직접 호출 또는 UI 후속 |
| 앱에서 로그인 후 `/login?error=AUTH_INVALID_APP_CODE` | 원타임 코드 60초 만료/재사용/길이 초과 — 사유는 의도적으로 구분 안 함 | 재로그인. 반복 시 앱 딥링크 스킴(`APP_SCHEME`)·시계 확인 |
| 푸시가 안 옴 | `EXPO_ACCESS_TOKEN` 없음(무인증 시도) / 디바이스 미등록 / 설정 off / 웹 브라우저(앱 아님) | `device_tokens` 행·`notification_settings.enabled`·`notification_logs.status/error_code` 확인. 실발송은 QA BLOCKED — 실기기 필요 |
| 게스트 예산안이 사라짐 | localStorage 30일 만료 / 브라우저 데이터 삭제 (정상) | 재작성 안내 |
| 401 `AUTH_TOKEN_REVOKED` | refresh 재사용 감지 → 전 세션 폐기 (정상 방어) | 재로그인. 빈발 시 탈취 의심 |

## QA 하네스 (`docs/테스트/harness/`)

| 증상 | 원인 | 조치 |
|------|------|------|
| `http_tests.py` 의 H-41 오탐 FAIL / H-13 공허 PASS | psql 검증의 DB 명이 `jaringobe_qa` 하드코딩이었음(재판정에서 환경변수화) | `QA_DB=<DATABASE_URL 의 DB 명>` 으로 실행 |
| S8-04 가 `delivered` 로 나와 FAIL | 시나리오의 수동 확정 시각이 eta 도달 이전이 아니었음(하네스 기대값 문제, 제품 결함 아님) | 재판정에서 기대값 동적화·R-05 추가. 1차 원문은 `git show 591463c:…` |

## 로그 확인
```bash
docker compose logs -f db
docker compose logs -f backend      # uvicorn 표준 출력. ★ app.* INFO 는 로거 구성 전까지 안 보임(BUG-011)
# 사이클 관측은 DB 로:
#   SELECT user_id, last_stage, stage_attempts, next_run_at FROM user_cycle_settings WHERE enabled;
#   SELECT id, status, blocked_reason, auto_confirm_at, delivery_eta, inbound_at, delivery_state FROM orders ORDER BY created_at DESC LIMIT 20;
```
로그에는 토큰·이메일·금액·재료명 원문을 남기지 않는 것이 규칙(CWE-532).

## 에스컬레이션
- 인증 우회·토큰 탈취 의심 → 보안 이슈: 해당 유저 refresh_tokens 전체 revoke 후 원인 분석
- 스키마 불일치 → 인프라 에이전트 (`alembic history`·`heads` 와 `docs/설계/db-schema.md` 대조)
- 예산 락 사용자가 한도 초과 금액으로 `auto_confirmed=true` 확정된 행이 발견되면 → **즉시 스케줄러 정지 + API 에스컬레이션** (설계상 존재해서는 안 되는 경로, QA R-01f 에서 0건 확인)
- 냉장고 재고가 주문 대비 2배로 늘어난 사용자 → `fridge_items.order_id` 별 등록 횟수 확인, 멱등 4번(inbound CAS) 위반 여부 → API 에스컬레이션
