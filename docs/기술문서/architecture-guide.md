# 아키텍처 가이드 (개발자용)

> 원본 설계: `docs/설계/architecture.md` (계약서, v1.10) — 이 문서는 신규 개발자 온보딩용 요약이다. 기준 시점: v0.2.0 (`feature/loop-cycle-base`, 2026-09-05, QA GATE 4 통과).

## 전체 구조 (v0.2.0 기준)

```
브라우저 / 앱 웹뷰(mobile/, Expo + react-native-webview)
   │  동일 오리진, httpOnly 쿠키          ↕ 브리지 postMessage {v:1,type,payload}
Next.js 14 (frontend/)  ── rewrites: /api/v1/* → BACKEND_URL
   │
FastAPI (backend/) ──── 카카오/구글 OAuth · 네이버 쇼핑 검색 · Claude API · Expo Push API
   │  lifespan asyncio 태스크 2개
   │    ├─ run_scheduler_loop  (식사 리마인더, 30초, notification/scheduler.py)
   │    └─ run_cycle_loop      (주간 사이클,  60초, cycle/scheduler.py)
   │  SQLAlchemy 2.0 async
PostgreSQL 16 (docker) — Alembic 리비전 0001 → 0012
```

- **CORS 를 쓰지 않는다**: 프론트가 `/api/v1/*` 를 백엔드로 프록시(rewrites)해 동일 오리진을 만든다. 백엔드는 Origin 검증 미들웨어(`POST/PUT/PATCH/DELETE` 대상)로 상태 변경 요청을 방어한다. 따라서 **GET 핸들러는 값을 바꾸는 부작용을 가져서는 안 된다**(security-guide 참조)
- **홈 셸 공유**: `/` 는 게스트(정적 샘플 매트릭스)와 회원이 같은 `HomeShell` 을 쓰고 데이터만 교체 주입. 회원 홈에는 `CycleStatusCard`·`AutoOrderCard` 가 추가된다
- **게스트 로직은 100% 클라이언트**: 게스트 입력은 서버로 보내지 않는다 (가입 시 `POST /budget/plans` 이전 1회 제외)
- **스케줄러는 HTTP 요청 컨텍스트가 없다**: 인증 미들웨어를 거치지 않으므로 서비스 계층이 `user_id` 를 인자로 강제한다(전역 세션·암묵적 현재 사용자 개념 없음)

## 디렉토리 규칙

| 위치 | 규칙 |
|------|------|
| `backend/app/domains/{도메인}/` | router(HTTP) → service(비즈니스) → models(SQLAlchemy). 라우터에 비즈니스 로직 금지. `cycle/` 은 추가로 `scheduler.py`(due 스캔 루프)·`policy.py`(환경변수 → 정책 객체) 를 가진다 |
| `backend/app/api/v1/router.py` | 도메인 라우터 집결점(composition root). `order` 라우터는 `create_order_router(get_order_cycle_context)` 로 사이클 컨텍스트를 **주입받아** 생성한다 |
| `backend/app/core/` | config(Settings)/security(JWT·state·쿠키·앱 로그인 코드)/deps/errors/ratelimit/schema(CamelModel) |
| `backend/alembic/` | 마이그레이션 단일 경로 — **인프라 에이전트 전담**, DDL 직접 실행 금지 |
| `frontend/src/features/{도메인}/` | 도메인 분류 준수, 컴포넌트+훅+API 클라이언트+테스트 동거 |
| `frontend/src/shared/` | api(fetch 래퍼)/ui/config(상수)/**bridge**(웹↔앱 브리지 프로토콜·zustand 스토어) |
| `mobile/` | Expo 앱 쉘(`App.tsx`, `src/webview.tsx`). 웹을 감싸기만 하며 도메인 로직 없음 |

## 도메인 현황 (v0.2.0)

| 도메인 | backend | frontend | 비고 |
|--------|---------|----------|------|
| auth | ✅ | ✅ | 카카오/구글 + 앱 로그인(`client=app` → 원타임 코드 → `/auth/app/session`). 애플 P1 |
| household · budget | ✅ | ✅ (온보딩·설정) | `budget.service` 가 예산 안분기(`prorate`·`cycle_limit`)의 소유자 |
| mealplan | ✅ | ✅ | `POST /mealplans` 202 비동기. 냉장고 → 식단 되먹임 프롬프트(모든 생성 경로) |
| fridge | ✅ | ✅ | 배송분 자동 등록(`source='delivery'`, `order_id` FK), 식사 완료 자동 차감 |
| store | ✅ (연동 상태 + 네이버 검색) | ✅ (설정) | 실계정 연동·결제 없음. 국가별 세트 KR 4 / US 2 |
| **order** | ✅ | ✅ (`/orders`) | 시뮬레이션 확정 + 사이클 상태 머신. `/orders/*` 는 order 소유 |
| **notification** | ✅ | ✅ (`/settings/notifications`) | Expo 푸시·디바이스 토큰·리마인더 스케줄러 |
| **cycle** | ✅ | ✅ (홈 카드·설정 카드) | 주간 자동 사이클 조정자 + 스케줄러 |
| subscription | 미구현 | — | 후속 |

## 주간 자동 사이클 (`cycle` 도메인) — 설계 3-9 요약

### 왜 별도 도메인인가
사이클은 mealplan·order·fridge·budget·store·notification **6개 도메인을 가로지르는 조정자**이고 자기 소유 테이블(`user_cycle_settings`)이 있다. order 안에 넣으면 order 가 식단을 만들고 냉장고에 쓰고 푸시를 보내는 God 도메인이 된다.

**의존 방향은 단방향으로 고정** — 이것이 실제 방지 장치다:
```
cycle ──→ mealplan.service / order.service / fridge.service(order 경유 원칙) / budget.service / store.connection_service / notification.service
역방향(mealplan·order·fridge → cycle) import 금지.  ※ order 라우터가 필요한 사이클 정보는 composition root 가 주입
```
주문 상태 머신과 `orders` 의 사이클 컬럼(`cycle_start`·`delivery_eta`·`inbound_at`·`auto_confirm_at`·`delivery_state`·`auto_confirmed`·`blocked_reason`·`reminded_at`·`delivery_confirm_attempts`)은 **order 도메인 소유**다.

### 시간 축 (사용자 로컬 시각 기준, UTC 저장)
`cycle_start` = 배송 기준일(로컬 date, **멱등 키**). weekly 프로파일 기본: D-5 식단 생성 → D-2 초안 → 초안 +24h 그레이스 자동확정 → `delivery_eta` = 확정 로컬일 + 스토어 리드일의 `CYCLE_STAGE_LOCAL_HOUR`(09시). 사용자별 **결정적 지터**(`crc32(user_id) % CYCLE_JITTER_MINUTES`)로 동시 폭주 방지. `next_run_at` 은 "미래의 로컬 시각"을 그때그때 UTC 로 환산(DST 안전). 타임존 변경 시 즉시 재계산.

### 스케줄러 구조 — 신규 인프라 없음
`notification/scheduler.py` 패턴을 그대로 재사용한다: **FastAPI lifespan asyncio 태스크 + partial index due 스캔**. **APScheduler / Celery / Redis 를 도입하지 않는다** (`pyproject.toml` 무변경). 정책 파라미터도 DB 테이블이 아니라 **환경변수**(`cycle/policy.py`, 파싱 실패 시 기본값 폴백 + 경고 로그).

한 tick(`process_cycle_tick`) = 독립 3스캔, 전부 partial index 커버 + `SELECT … FOR UPDATE SKIP LOCKED`, 재실행 안전:

| # | 스캔 | 인덱스 | 처리 |
|---|------|--------|------|
| ① | `user_cycle_settings` 사용자 단계 | `ix_cycle_settings_due (next_run_at) WHERE enabled AND next_run_at IS NOT NULL` | 활성 판정 → 식단 자동 생성(D-5, 백그라운드 태스크) 또는 초안 생성(D-2) → `last_stage`·`next_run_at` 전진 |
| ② | `orders` 그레이스 자동확정 | `ix_orders_autoconfirm_due (auto_confirm_at) WHERE status='draft' AND auto_confirm_at IS NOT NULL` | 5중 게이트 통과 시 재계산 스냅샷으로 확정, 아니면 `awaiting_user` + 재알림 1회 |
| ③ | `orders` 배송 → 냉장고 등록 | `ix_orders_inbound_due (delivery_eta) WHERE status='confirmed' AND inbound_at IS NULL AND delivery_state <> 'unknown'` | `inbound_at` compare-and-set → needed 라인만 `fridge.add_items(source='delivery', order_id)` → `fridge_inbound` 푸시 |

- 루프는 개별 사용자/주문 예외를 삼키고 계속 돈다(`logger.exception` 후 다음 항목). tick 전체 실패도 다음 tick 계속
- 사용자 단계 상태 머신(`last_stage`): `NULL → generated|skipped_dormant|deferred_quota|skipped_user → drafted`, 생성 실패 `generate_failed`(익일 1회 재시도), 초안 실패는 `stage_attempts` + 1/5/15분 백오프 후 4회차 폴백 초안(시세 없이 needed 만) — 루프를 멈추지 않는다
- 자동확정 5중 게이트(스캔 ②): ⓪ 이 사이클 confirmed 존재 → 조용히 `expired` ① `auto_confirm=false` → `AUTO_CONFIRM_OFF` ② US → `US_NO_PRICE` ③ 스토어 미연동 → `STORE_DISCONNECTED` → **서버가 확정 스냅샷 1회 재계산** → ④ 재계산 미매칭 > 30% → `UNMATCHED_RATIO` ⑤ 재계산 총액 > `cycle_limit` 이고 예산 락 → `BUDGET_EXCEEDED`(락 해제면 경고만) ⑥ 식단 `over_budget` → `MEALPLAN_OVER_BUDGET`. 판정한 금액과 저장되는 금액이 같다(BUG-001 수정)

### ⚠ 단일 인스턴스 전제 — 멀티 인스턴스 중복 실행 위험
> 동일 DB 를 보는 앱 인스턴스가 2대 이상이면 **스캔 ①이 같은 사용자에게 식단 생성을 중복 트리거**할 수 있다(LLM 비용 2배). ②·③은 부분 유니크 인덱스 / `inbound_at` CAS 가 최종 방어선이라 중복 확정·중복 등록은 나지 않지만 **①은 DB 로 막을 수 없다.**
> - 운용 회피책: 인스턴스 중 **1대만** `CYCLE_SCHEDULER_ENABLED=true` (리마인더의 `REMINDER_SCHEDULER_ENABLED` 와 동일 방식)
> - `uvicorn --workers N` 도 멀티 인스턴스다. 컨테이너 진입점(`docker-entrypoint.sh`)은 `--workers` 미지정(1 프로세스)
> - 오토스케일·다중 워커로 형상을 바꾸면 **설계 재소집**(분산 락 또는 리더 선출). 이번 범위 밖
> - 인메모리 rate limiter(`core/ratelimit.py`)도 같은 이유로 멀티 인스턴스 시 Redis 교체 대상

### 멱등 4중 (FR-816 — 자동화의 전제 조건)
| # | 지점 | 장치 |
|---|------|------|
| 1 | 자동 식단 생성 (사용자당 사이클 1회) | `last_generated_cycle_start` 비교 — **접수 시점에 즉시 기록** |
| 2 | 초안 (사이클당 1건) | `uq_orders_open_cycle (user_id, cycle_start) WHERE status IN ('draft','awaiting_user')` |
| 3 | 확정 (사이클당 1건) | `uq_orders_confirmed_cycle (user_id, cycle_start) WHERE status='confirmed'` — `IntegrityError` 는 정상 스킵 |
| 4 | 냉장고 등록 (주문당 1회) | `UPDATE orders SET inbound_at=now() WHERE id=:id AND inbound_at IS NULL RETURNING id` → 행이 나올 때만 등록, 같은 트랜잭션 |

> 4번의 순서(**먼저 마킹 → 그 다음 냉장고 쓰기, 한 트랜잭션**)를 뒤집지 말 것. 냉장고를 먼저 쓰고 마킹하면 그 사이의 크래시가 곧 재고 인플레다.

### 비용 상한 (FR-817) · 활성 판정 (FR-802)
- 사용자당 사이클 1회 + **전체 일일 상한** `CYCLE_DAILY_GENERATION_LIMIT`(200, UTC 일 기준). 도달 시 `deferred_quota` 로 익일 이월 — 실패가 아니다. 수동 생성(`mealplan_user_limiter` 5회/분)은 별도이며 자동 카운터에 집계하지 않는다. **이 방어선은 임의 제거 금지**
- 활성 = 지난 사이클 구간 `meals.completed_at` ≥ `CYCLE_ACTIVE_COMPLETION_MIN`(1) AND `users.last_seen_at` ≥ now − `CYCLE_ACTIVE_SEEN_DAYS`(14). `last_seen_at` 갱신은 인증 쓰기 경로 3곳만(OAuth 콜백 / refresh / app session). 신규 사용자는 자동 대상이 아니다(첫 식단은 홈 CTA). 탈락 시 `dormant_since` + `cycle_paused` 푸시 1회, 홈 복귀 카드는 그 사이클에 1회(localStorage 억제)

### 냉장고 → 식단 되먹임 (FR-805/806)
`mealplan/fridge_hint.py::build_fridge_hint(db, user_id, region)` 이 프롬프트 힌트 문자열을 조립하고, `mealplan.service` 의 생성 경로가 이를 `generator.generate_meals(..., fridge_hint)` 에 넘긴다(제너레이터는 DB 를 모르는 순수 함수 유지). 재고를 `(name.lower(), unit)` 로 합산, 임박(`expires_at <= today + CYCLE_EXPIRING_DAYS[country]`) 최대 15줄 + 일반 최대 25줄, 절삭 시 `...and N more items`. **"냉장고에 있다고 수량을 줄이지 마라"** 규칙이 핵심 — 감산은 서버 `compute_shortfall` 이 하므로 LLM 이 미리 빼면 이중 감산이다. 자동 사이클 전용이 아니라 수동·재생성·월간 전부 적용. mock LLM 은 힌트를 무시한다(알려진 한계).

### 배송 → 냉장고 등록 (FR-819~823)
```
확정: delivery_eta = (로컬 confirmed 날짜 + lead_days(store)) 의 09:00 로컬 → UTC   (확정 즉시 등록은 제거됨)
eta 도달: 스캔 ③ → CAS(inbound_at) → needed 라인만 add_items(source='delivery', order_id, expires_at=NULL) → fridge_inbound 푸시
보정: POST /orders/{id}/delivery {received:false} → order_id 기준 등록분 롤백 + eta = 응답시각 + 1일 + attempts++ ; 3회 → delivery_state='unknown' (스캔 ③ 제외)
취소: POST /orders/{id}/cancel (cycle_start + 7일 창) → 남아 있는 배송분 행만 삭제, 소비(차감)분은 되돌리지 않음(음수 재고 금지)
```
`fridge_items.order_id` FK 가 롤백의 기준이다(이름·수량 매칭은 사용자가 수량을 고치면 즉시 틀린다). `covered` 라인은 등록하지 않는다.

### 예산 안분기 — `budget.service`
`_prorate` 를 mealplan 에서 budget 도메인으로 옮겼다: `prorate(monthly, days)` · `prorate_remaining_month(as_of, monthly)`(월간 플랜 전용, 결과 불변) · `cycle_limit(db, user, cycle_start, cycle_days, timezone_name)`. 주간 한도 = 월초부터 `min(cycle_start + cycle_days, 익월 1일)` 까지 누적 안분액 − 같은 구간 `orders.cycle_start` 기준 확정 합계(음수는 0). 앞선 사이클 잔액이 이월되고 다음 달 예산을 끌어쓰지 않는다. 엔드포인트로 승격하지 않음 — UI 가 필요한 값은 `GET /cycle` 의 `weeklyLimit` 뿐.

## 앱 웹뷰·푸시 (notification 도메인) 요약
- `mobile/` Expo 쉘이 웹을 웹뷰로 감싸고 UA 에 ` JaringobeApp/{v} ({os})` 접미사를 붙인다. 웹은 `isApp()` = UA 마커 + `window.ReactNativeWebView` 이중 확인
- 브리지 메시지 `{v:1, type, payload}` — 앱→웹 `BRIDGE_READY`·`PERMISSION_STATUS`·`PUSH_TOKEN`, 알 수 없는 type/상위 v 는 무시(전방 호환). `BridgeProvider`(`app/[locale]/layout.tsx`)가 수신하고 `PUSH_TOKEN` 은 `PUT /notifications/devices` 로 등록(미로그인 401 이면 로그인 완료 시 지연 등록)
- 리마인더 스케줄러(30초): `notification_settings` due 행을 `ix_notification_settings_due` 로 스캔, 발송 직전 3중 재확인(최신 플랜의 당일 끼니 존재 / 미완료 / enabled), `next_send_at` 익일 재계산. 사이클 알림 3종(`order_approval`·`fridge_inbound`·`cycle_paused`)은 리마인더가 아니라 이벤트 시점 발송
- 앱 로그인: `authorize?client=app` → state 에 `client` 서명 → 콜백이 원타임 코드(SHA-256 해시만 DB, 60초) 를 `{APP_SCHEME}://auth?code=` 로 → 앱이 웹뷰에서 `GET /auth/app/session?code=` 호출 → 쿠키 세팅

> 앱 웹뷰·푸시의 기획서(`앱-웹뷰-푸시알림.md`)·설계(`mobile-app.md`, api-spec §6-A 등)는 통합 병합 시 이 브랜치에 들어오지 않았다. 원문은 `git show 836f0ae:docs/설계/mobile-app.md` 로 볼 수 있다 (릴리즈 노트 v0.2.0 알려진 이슈).

## 새 기능 추가 시 흐름
1. `/기획시작` → GATE 1 → `/설계시작` → GATE 2 (api-spec.md 갱신은 설계 변경 프로세스 필수)
2. DB 변경 시 `/인프라시작` (GATE 3) — 모델은 마이그레이션과 1:1 유지(테스트가 `compare_metadata` diff 0건 검증)
3. `/API시작` + `/UI시작` → `/QA시작` (GATE 4) → `/문서시작`
4. 사이클에 새 단계·게이트를 넣을 때: 정책값은 `Settings` + `policy.py` 에 추가(테이블 금지), 스캔은 partial index 를 먼저 설계, 재실행 안전(멱등)을 먼저 증명
