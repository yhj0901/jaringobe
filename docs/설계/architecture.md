# 아키텍처 설계서 — 게스트 홈 + 소셜 로그인 (초기 스캐폴딩 포함)

> 대상 기획: `docs/기획/게스트홈-진입경험.md`, `docs/기획/로그인-소셜인증.md`
> 본 문서는 프로젝트 최초 설계로, **모노레포 스캐폴딩 구조** 를 함께 확정한다. 이후 기능은 이 구조 위에 증분한다.

## 1. 전체 구성

```
[브라우저]
   │  동일 오리진 (쿠키 httpOnly)
   ▼
[Next.js 14+ (frontend/)] ── SSG/RSC 렌더 + 게스트 로직(클라이언트)
   │  rewrites 프록시: /api/v1/* → FastAPI
   ▼
[FastAPI (backend/)] ── auth/budget 도메인 라우터
   │  SQLAlchemy 2.0 async
   ▼                          ┌─ [카카오 OAuth]
[PostgreSQL 16] (docker)      ├─ [구글 OAuth]
                              └─ [애플 OAuth (P1)]
```

**핵심 결정**
| # | 결정 | 근거 |
|---|------|------|
| A-1 | 프론트→백 통신은 **Next.js rewrites 프록시** (`/api/v1/:path*` → 백엔드) | 동일 오리진화로 httpOnly 쿠키 인증이 CORS 설정 없이 동작. 배포 시에도 프록시 유지 |
| A-2 | 홈 라우트는 `/` 단일 — 게스트/회원 모두 같은 **홈 셸 컴포넌트**에 데이터 소스만 교체 주입 | 기획 FR-101 (게스트 홈 = 로그인 후 홈의 기반). 회원 실데이터 연결은 후속 도메인 설계에서 |
| A-3 | 게스트 상태 로직은 100% 클라이언트 (정적 샘플 매트릭스 + localStorage) | 기획 원칙: 게스트 입력 서버 전송 금지 (가입 시 이전 1회 제외) |
| A-4 | OAuth 는 백엔드 주도 Authorization Code — 브라우저는 백엔드 `/authorize` 로 진입해 provider 를 거쳐 백엔드 `/callback` 에서 쿠키를 받고 프론트로 302 | 시크릿·토큰 교환을 전부 서버에 격리. provider 어댑터 패턴 |
| A-5 | `budget_plans` 테이블은 **최소 v0** 로 신설 (게스트 예산안 이전 저장처) | FR-108 구현 불가 문제 해소. budget 본설계에서 확장 전제 (`db-schema.md` 참조) |

## 2. 디렉토리 구조 (스캐폴딩 확정)

```
frontend/
  next.config.mjs            # rewrites: /api/v1/* → BACKEND_URL
  messages/ko.json en.json   # i18n (동시 수정 필수)
  src/
    app/[locale]/
      layout.tsx             # next-intl provider, 로캘 라우팅
      page.tsx               # 홈 (게스트/회원 공용 셸) — RSC
      login/page.tsx         # 로그인 페이지
      onboarding/page.tsx    # 온보딩 (라우트 예약 — 본 구현은 household 기획)
    features/                # 도메인 분류 준수
      home/                  # 홈 셸 컴포넌트 (식단 카드/예산 무드/냉장고/주문 카드)
      guest/                 # 게스트 상태, 타이밍 프롬프트, 예산안 플로우, 샘플 매트릭스
      auth/                  # 로그인 버튼, 세션 훅, 가입 게이트 모달
      budget/                # 예산안 이전(guest→plan) 클라이언트
    shared/
      api/                   # fetch 래퍼 (에러 code → i18n 매핑)
      ui/                    # 공용 UI (바텀시트, 배지 등)
      config/                # 상수 (프롬프트 타이밍 등)

backend/
  pyproject.toml             # uv 관리
  app/
    main.py                  # FastAPI 앱, 미들웨어(Origin 검증, rate limit)
    core/
      config.py              # pydantic-settings (.env)
      security.py            # JWT 발급/검증, state 서명, 쿠키 정책
      deps.py                # get_current_user 등 의존성
    db/
      session.py base.py     # async engine/session, DeclarativeBase
    domains/
      auth/
        router.py            # /api/v1/auth/*, /api/v1/users/me
        service.py schemas.py models.py   # User, AuthIdentity, RefreshToken
        adapters/
          base.py            # OAuthAdapter 프로토콜 (3사 공통 — 애플 P1 도 동일 인터페이스)
          kakao.py google.py apple.py
      budget/
        router.py service.py schemas.py models.py  # BudgetPlan (v0)
  alembic/                   # 마이그레이션 (인프라 에이전트 전담)
  tests/                     # pytest + httpx

docker/ · docker-compose.yml # postgres 16 (인프라 에이전트)
```

**(v1.6 증분 — 자동주문 P0)** 신규 도메인 폴더. 기존 스캐폴딩 트리는 유지하고 아래만 추가한다.

```
backend/app/domains/order/     # router.py · service.py · schemas.py · models.py
frontend/src/features/order/    # 리뷰 페이지·API 클라이언트 (AutoOrderCard 복제 금지)
frontend/src/app/[locale]/orders/page.tsx   # /orders 리뷰 (인증 필수)
```

- `AutoOrderCard` 는 `features/home/` 에 유지하고 member CTA/카피만 props·네임스페이스로 확장한다.
- 백엔드 레이어링: `router(HTTP) → service(비즈니스) → models(SQLAlchemy)`. 라우터에 비즈니스 로직 금지
- `/users/me` 는 리소스상 users 지만 계정 도메인이므로 **auth 도메인 라우터**에서 제공 (별도 users 도메인 생성 안 함)

## 3. 주요 흐름

### 3-1. 게스트 홈 (서버 무관)
```
GET / → RSC 가 홈 셸 + 기본 샘플 렌더 (SSG 가능)
클라이언트 하이드레이션 후:
  localStorage 게스트 예산안 있음(30일 내) → 해당 매트릭스 셀로 홈 갱신
  없음 → 기본 샘플 + 체류 10초/스크롤 유휴 감지 → 프롬프트 바텀시트
예산안 작성 → 매트릭스 조회(클라이언트) → 홈 위젯 일괄 갱신 + localStorage 저장
```

### 3-2. 소셜 로그인 (백엔드 주도)
```
[프론트] 버튼 클릭 → location = /api/v1/auth/kakao/authorize?next=/
[백엔드] state 서명 토큰 생성 → provider 인가 URL 302
[provider] 사용자 동의 → /api/v1/auth/kakao/callback?code&state
[백엔드] state 검증 → code 교환 → 프로필 정규화(NormalizedProfile)
        → auth_identities upsert 조회 (신규면 users 생성)
        → refresh 저장(해시) + 쿠키 세팅(access/refresh)
        → 302 {next}?login=success (실패 시 /login?error={code})
[프론트] GET /users/me → onboardingCompleted/hasBudgetPlan 로 분기
```

### 3-3. 게스트 예산안 이전 (가입 직후 1회)
```
로그인 완료 + localStorage 게스트 예산안 존재 + hasBudgetPlan=false
  → POST /api/v1/budget/plans (서버 전량 재검증)
    201 → localStorage 삭제 → 온보딩 스킵(확인 화면) → 홈(예산안 반영)
    409 BUDGET_PLAN_EXISTS → localStorage 삭제만 (기존 회원 재로그인 케이스)
    422 → 값 폐기(변조 의심) → 일반 온보딩으로
```

### 3-4. 회원 홈 (v1.1 — 회원홈-식단연결)
```
로그인 홈 진입 → GET /users/me
  hasBudgetPlan=false → BudgetDraftFlow(재사용) → POST /budget/plans(onboarding)
  → GET /mealplans/latest
      404 → 빈 상태 히어로 → 생성 시트 → POST /mealplans (LLM, 폴백 내장) → 표시
      200 → MealPlanResponse → ViewModel 매핑 → HomeShell(mode=member)
냉장고/자동주문 카드는 "준비 중" 잠금 (fridge/order 도메인 구현 시 해제)
```
- **v1.6**: 자동주문 잠금은 **3-6** 에서 해제. 냉장고 카드는 기존 `/fridge` 활성 유지. 식단 탭 프리미엄 잠금은 유지.


### 3-5. 지역 전환 (v1.5 — 글로벌-지역전환, 수동)
```
[설정] "지역·통화" 토글 → 확인 시트 → PUT /api/v1/users/me/region {country}
[백엔드] country(KR/US) 검증 → currency 매핑(KR→KRW / US→USD) → users.country·currency UPDATE → 200 UserMe
[프론트] GET /users/me 재조회 → 통화(MoneyText)·스토어 세트·"글로벌" 배지 즉시 반영
소급 변환 없음: 기존 budget_plans/meal_plans 저장 통화 유지 (FR-606)
```
- store 연동 조회/변경은 `user.country` 기준 세트로 분기(KR 4 / US 2). 지역 전환 시 타 국가 연동 행은 **삭제 없이 응답 필터만** — 재전환 시 상태 복원
- 담당 격리: users region 은 **auth 도메인 라우터**(GET /users/me 와 동일 위치), 국가별 스토어 세트는 우리 소유 `connection_*` 파일에서 분기. store 도메인 **DB CHECK 변경(0008)은 팀원 리뷰 필수**(연동·어댑터 본 파일 무접촉)

### 3-6. 자동주문 P0 (v1.6 — 시뮬레이션 확정 + 동적 감산)
```
[회원 홈 /]
  GET /users/me · GET /stores/connections
  ├─ 스토어 0개 연동 → AutoOrderCard 비활성 톤 + CTA → /settings
  └─ 1개 이상 연동 → AutoOrderCard 활성
        GET /api/v1/orders/preview  (백그라운드, 연동 없어도 200)
          needed 칩 + CTA "장바구니 보기" → /orders

[/orders]
  GET /orders/preview (리뷰 본문)
  명시 탭 → POST /api/v1/orders { "store": "<country store>" }
             서버가 preview 를 **재계산** (클라이언트 라인 불신, CWE-602)
             status=confirmed · simulation=true · frequency=weekly
             needed 수량만 fridge inbound source=order (covered 는 inbound 금지)
  확정 후 GET /orders/latest 로 스냅샷·다음 제안일(+7일, 표시만) 재조회
```

- **실결제 없음**. 네이버 키 있는 KR 만 기존 `store.build_cart`(mall=`kurly`) 로 추정가. 키 없으면 `matched=false` + total 0. **US 는 네이버 호출 금지** — needed 만, 가짜 USD 금지 (`estimatedTotal.amount="0.00"`, currency=USD).
- `orders.store` 는 사용자가 연동한 스토어(후속 실결제 대상)이지 네이버 mall 필터가 아니다. 쿠팡 연동 중이어도 추정 카피에 "네이버 쇼핑(컬리) 검색 기준"을 명시.
- 프론트는 `POST /store/cart` 로 재료를 밀어 preview 를 우회하지 않는다. 확정 inbound 는 order 서비스가 내부 `fridge.add_items` 호출 (프론트 이중 POST 금지).
- 기존 `POST /mealplans/{id}/cart` 는 완료 끼니를 빼지 않고 persist/inbound 도 없다 — **삭제하지 않고 UI 에서 쓰지 않음**. 제품 접점은 `/orders/*`.
- 게스트: AutoOrderCard 기존 유지, 주문 API 호출·persist 금지.
- 스케줄러(APScheduler/cron/Redis) P0 도입 금지. `next_suggested_at` 은 컬럼+표시만.
- 신규 스토어 어댑터(쿠팡/월마트 검색 API) 를 만들지 않는다 — 기존 Naver `build_cart` 재사용만.
## 3-9. 주간 자동 사이클 (v1.8 — 루프완결-주간사이클)

> 기획: `docs/기획/루프완결-주간사이클.md` (GATE 1 승인). 본 절이 13장 인계사항 9건 + 되먹임·스케줄러·멱등·비용 상한의 설계 확정본이다.
>
> **문서 정합 안내(머지 전제)**: 본 증분은 `feature/auto-order-p0`(order 도메인, 설계 v1.6) 와 `feature/app-webview-push`(notification 도메인·mealplan 202 비동기, 설계 v1.5) 가 **main 에 머지된 상태**를 전제로 한다. 두 브랜치가 각각 독립 번호(v1.6 / v1.5)로 같은 문서를 증분했으므로, 본 증분은 충돌을 피해 **v1.8** 로 통일 번호를 쓴다. 절 번호도 두 브랜치가 쓴 번호(architecture 3-5~3-8, api-spec 6-A/7/8, db-schema 2-8)를 비켜 배정했다.

### 3-9-1. 도메인 배치 — 신규 `cycle` 도메인 (인계사항 5)

**결정: `order` 확장이 아니라 신규 `cycle` 도메인을 만든다.**

| 판단 기준 | 적용 |
|-----------|------|
| **데이터 소유** | `user_cycle_settings` 라는 자기 소유 테이블이 있다. 어느 기존 도메인의 부속물도 아니다 |
| **관심사** | 사이클은 mealplan·order·fridge·budget·store·notification **6개 도메인을 가로지르는 조정자**다. order 안에 넣으면 order 가 식단을 생성하고 냉장고에 쓰고 푸시를 보내는 God 도메인이 된다 |
| **리소스 경로** | `/api/v1/cycle*` 은 `/orders` 와 별개 리소스 (REST 명사 분리) |
| **수명주기** | 사이클 설정은 주문이 하나도 없어도 존재한다 (온보딩 직후) |

**의존 방향을 단방향으로 고정한다 — 이것이 God 도메인화를 막는 실제 장치다.**

```
cycle ──→ mealplan.service   (start_meal_plan_generation / run_meal_plan_generation)
      ──→ order.service      (create_draft / confirm / cancel / mark_inbound / expire)
      ──→ fridge.service     (add_items / compute_shortfall)   ※ order 경유가 원칙, 직접 호출은 금지
      ──→ budget.service     (cycle_limit — 3-9-4)
      ──→ store.connection_service (연동 상태 조회)
      ──→ notification.service / sender (알림 발송)

역방향(mealplan/order/fridge → cycle) import 금지.
```

- **주문 상태 머신과 `/orders/*` 엔드포인트는 계속 `order` 도메인 소유**다. `orders` 에 추가되는 `cycle_start`·`delivery_eta`·`inbound_at`·`auto_confirm_at`·`delivery_state`·`auto_confirmed` 컬럼도 order 도메인 모델이 소유한다. cycle 은 order 의 공개 서비스 함수만 호출한다.
- 사이클 상태(`user_cycle_settings`)와 주문 상태(`orders`)를 **분리**한다. 스케줄러는 사용자 단계 스캔과 주문 단계 스캔을 별도로 돈다 (3-9-3). 사용자 스테이지 머신을 주문 상태에 묶으면 재시도가 꼬인다.

**디렉토리 증분** (기존 스캐폴딩 트리 유지, 아래만 추가)

```
backend/app/domains/cycle/
  models.py      # UserCycleSettings
  schemas.py     # CycleStateOut / CycleSettingsUpdateRequest
  router.py      # GET /cycle · PUT /cycle/settings · POST /cycle/skip
  service.py     # 사이클 계산(날짜/한도/활성판정) + 단계 실행
  scheduler.py   # lifespan asyncio 루프 (notification/scheduler.py 패턴 재사용)
  policy.py      # 정책 파라미터 해석 (env → 프로파일/국가별/스토어별)
frontend/src/features/cycle/   # 상태 카드 · 설정 카드 · API 클라이언트
```

### 3-9-2. 시간 축 (사용자 로컬 시각 기준, UTC 저장)

`anchor_weekday` 는 **0=일요일 … 6=토요일** (JS `Date.getDay()` 규약 — 프론트 요일 선택 UI 와 동일). Python 변환은 `py_weekday = (anchor_weekday + 6) % 7`.

```
D = cycle_start = 다음(오늘 포함) anchor_weekday 의 사용자 로컬 날짜   ← 사이클 멱등 키
    delta = (anchor_weekday - jsday(today_local)) % 7 ;  D = today_local + delta
```

| 프로파일 | 사이클 길이 | 식단 생성 | 초안 생성 | 그레이스 | 배송(냉장고 등록) |
|----------|-------------|-----------|-----------|----------|-------------------|
| `weekly` (기본) | 7일 | D−5 09:00 | D−2 09:00 | 초안 +24h | `delivery_eta` ≈ D 09:00 |
| `biweekly` (주 2회) | 3/4일 교대 (앵커 = `anchor_weekday`, `(anchor_weekday+3)%7`) | D−2 09:00 | D−1 09:00 | 초안 +12h | `delivery_eta` ≈ D 09:00 |

- 시각(09:00)·리드일수·그레이스는 프로파일 단위 정책 파라미터(3-9-7). 주 2회에서 리드일수를 그대로 쓰면 단계가 겹치므로 **프로파일별 값을 따로 둔다**(수식 클램프보다 예측 가능).
- **지터**: `jitter_minutes = crc32(user_id.bytes) % CYCLE_JITTER_MINUTES` 를 각 단계 시각에 더한다. **결정적**이어야 재계산 때 흔들리지 않는다 (랜덤 금지). 기획 5-4 의 "같은 분에 몰려 자기 rate limit 을 치는" 문제 방어.
- **DST**: `next_run_at` 은 항상 "미래의 특정 로컬 시각"을 그때그때 UTC 로 환산해 저장한다 (`notification.service.compute_next_send_at` 과 동일 패턴). 전환일에도 하루 1회 실행이 보장되고 중복·누락이 없다.
- **타임존 변경**: `PUT /cycle/settings` 에서 `timezone` 이 바뀌면 `next_run_at` 을 즉시 재계산한다.

### 3-9-3. 스케줄러 구조 (신규 인프라 도입 없음)

`feature/app-webview-push` 의 `notification/scheduler.py` 패턴을 그대로 재사용한다 — **FastAPI lifespan asyncio 태스크 + partial index due 스캔**. APScheduler / Celery / Redis 를 도입하지 않는다 (`pyproject.toml` 무변경).

```
lifespan
 ├─ run_scheduler_loop(...)        # 기존: 식사 리마인더 (30초)
 └─ run_cycle_loop(interval=60s)   # 신규: 사이클 (CYCLE_SCHEDULER_ENABLED 로 개별 on/off)
```

한 tick 이 도는 **3개의 독립 스캔** — 전부 partial index 커버, 전부 재실행 안전:

| # | 스캔 | 조건 | 처리 |
|---|------|------|------|
| ① | `user_cycle_settings` 단계 | `enabled AND next_run_at IS NOT NULL AND next_run_at <= now` | 활성 판정 → 식단 자동 생성(D−5) 또는 초안 생성(D−2) → `last_stage`·`next_run_at` 전진 |
| ② | `orders` 그레이스 자동확정 | `status='draft' AND auto_confirm_at IS NOT NULL AND auto_confirm_at <= now` | 5중 게이트(3-9-5) 통과 시 확정, 아니면 `awaiting_user` |
| ③ | `orders` 배송 → 냉장고 등록 | `status='confirmed' AND inbound_at IS NULL AND delivery_state <> 'unknown' AND delivery_eta <= now` | needed 라인 inbound + `inbound_at` 기록 + 보정 알림 |

- 각 스캔은 `SELECT ... FOR UPDATE SKIP LOCKED` 로 대상 행을 잠그고 처리한다. 단일 인스턴스에서는 무해하고, 멀티 인스턴스에서도 중복 처리를 상당 부분 막는다.
- 루프는 개별 사이클 예외를 삼키고 계속 돈다(스케줄러 정지 방지) — 기존 `run_scheduler_loop` 와 동일.
- **CWE-639**: 배치라는 이유로 전역 쿼리를 쓰지 않는다. due 스캔이 대상 행을 고르면, 그 뒤의 모든 조회·변경은 반드시 해당 `user_id` 로 스코프한다.

**사용자 단계 상태 머신** (스캔 ① 만 사용. 확정·등록은 주문 행이 소유)

```
(행 생성)  last_stage=NULL         next_run_at = 다음 D−5
   ├─ 휴면(활성 판정 탈락) ──→ last_stage='skipped_dormant'   next_run_at = 다음 사이클 D−5   (생성 안 함)
   ├─ 일일 상한 도달      ──→ last_stage='deferred_quota'    next_run_at = 익일 동일 로컬시각
   ├─ 이번 사이클 스킵     ──→ last_stage='skipped_user'      next_run_at = 다음 사이클 D−5
   └─ 생성 접수           ──→ last_stage='generated'         next_run_at = 이번 사이클 D−2
                                   └ 생성 실패 → last_stage='generate_failed', next_run_at = 익일 동일시각 (1회 한정)
   last_stage='generated' + D−2 도달
   └─ 초안 생성           ──→ last_stage='drafted'           next_run_at = 다음 사이클 D−5
         └ 초안 실패 → stage_attempts++ , next_run_at = now + 백오프(1/5/15분). 3회 초과 시
            시세 없이 needed 목록만으로 초안 생성(matched 전량 false) — 루프를 멈추지 않는다
```

**멀티 인스턴스 경고 (배포 형상 제약 — 반드시 지킬 것)**

> 본 스케줄러는 **단일 인스턴스 전제**다. 동일 DB 를 보는 애플리케이션 인스턴스가 2개 이상이면 스캔 ①이 같은 사용자에게 식단 생성을 **중복 트리거**할 수 있다(LLM 비용 2배). 스캔 ②·③은 DB 제약(부분 유니크 인덱스 / `inbound_at` compare-and-set)이 최종 방어선이라 중복 확정·중복 등록은 발생하지 않지만, **①은 DB 로 막을 수 없다**.
>
> - 운용 회피책: 인스턴스 중 **1대만** `CYCLE_SCHEDULER_ENABLED=true` 로 둔다 (기존 `REMINDER_SCHEDULER_ENABLED` 와 동일 방식).
> - 형상 변경(오토스케일·다중 워커) 시 **설계 재소집** — 분산 락 또는 리더 선출이 필요하다. 이번 범위 밖 (기획 Out of Scope).
> - 참고: `uvicorn --workers N` 도 멀티 인스턴스다. 프로세스 1개(`--workers 1`)로 배포하거나 스케줄러 전용 프로세스를 분리한다.

### 3-9-4. 예산 안분기 재배치 — `_prorate` → `budget` 도메인 (인계사항 3)

**결정: 엔드포인트로 승격하지 않는다. `mealplan/service.py` 의 private `_prorate` 를 `budget` 도메인의 공개 서비스 함수로 옮긴다.**

- 근거: 안분 계산의 소유자는 예산 도메인이다. 소비자는 mealplan(월간)·cycle(주간 한도)·order(예산 게이트) 3곳이며, **UI 가 직접 필요로 하는 값은 `GET /cycle` 의 `weeklyLimit` 뿐**이므로 전용 엔드포인트를 만들 이유가 없다(엔드포인트를 늘리면 계약 표면만 커진다).

```python
# backend/app/domains/budget/service.py
def prorate(monthly: Decimal, days: Iterable[date]) -> Decimal:
    """일수 비례 안분 — 각 날짜가 속한 달의 일수로 나눈 몫의 합."""
    return sum(monthly / days_in_month(d) for d in days).quantize(_CENT, ROUND_HALF_UP)

def prorate_remaining_month(as_of: date, monthly: Decimal) -> Decimal:
    """기존 _prorate 와 수학적으로 동일 (monthly × 남은일수/그달일수). monthly 플랜 전용."""
    return prorate(monthly, month_days_from(as_of))

async def cycle_limit(db, user, cycle_start: date, cycle_days: int,
                      *, timezone_name: str = "Asia/Seoul") -> Decimal:   # v1.9: timezone_name 표기 보정
    """이번 사이클에 쓸 수 있는 금액 = 월 누적 안분액 − 같은 누적 기간의 기확정 합계 (음수는 0)."""
    # 예산안 없음 → 409 BUDGET_PLAN_REQUIRED (GET /cycle 은 호출 전에 예산안 존재를 확인해 weeklyLimit=null 로 우회)
    accrual_end = min(cycle_start + cycle_days, cycle_start 소속 월의 익월 1일)
    share     = prorate(budget.amount, [cycle_start 소속 월의 1일, ..., accrual_end 직전])
    committed = Σ orders.estimated_total
                WHERE user_id=? AND status='confirmed'
                  AND confirmed_at ∈ [cycle_start 가 속한 달의 로컬 1일 00:00, accrual_end 00:00)
                      → timezone_name 기준 로컬 → UTC 환산 (호출자가 user_cycle_settings.timezone 을 넘긴다)
    return max(Decimal("0"), share - committed).quantize(_CENT, ROUND_HALF_UP)
```

- 사이클별 단일 몫에서 월 누적 확정액을 빼면 2회차부터 한도가 0으로 붕괴하므로, **안분액과 확정액 모두 월초부터 이번 사이클 종료까지의 같은 누적 구간**을 사용한다. 앞선 사이클에서 남긴 금액은 다음 사이클로 이월되고, 각 사이클이 정상 예산을 썼다면 다음 한도는 새로 누적된 일수 몫이 된다.
- `prorate_remaining_month` 는 기존 `_prorate` 와 **결과가 완전히 동일**하다(달이 하나뿐이므로 `monthly × remaining/dim`). `build_monthly_plan` 의 동작은 바뀌지 않는다.
- 사이클이 달 경계를 넘으면 이번 계산은 `cycle_start` 소속 월의 말일까지로 자른다. 다음 달 초의 미사용 일수 몫은 다음 달 첫 사이클 누적액에 포함되므로 월별 예산·확정액의 기간이 섞이지 않는다.
- 통화는 `budget_plans.currency` 를 그대로 따른다. `Decimal` + 통화코드 쌍, float 금지.
- **v1.9 대조(2026-09-04)**: 위 수식과 `backend/app/domains/budget/service.py::cycle_limit` 구현이 **일치**함을 확인했다 — `month_start`/`next_month`(12월 롤오버 포함)/`accrual_end` 계산, `prorate` 범위 `[month_start, accrual_end)`, `confirmed_at` 범위의 로컬→UTC 환산, `status='confirmed'` 한정, `max(0, share − committed)` 및 소수 2자리 반올림까지 동일. 문서 쪽 차이는 시그니처의 `timezone_name` 키워드 인자 누락뿐이었고 본 버전에서 보정했다. 호출자 2곳(`GET /cycle` 의 `weeklyLimit`, 자동확정 게이트 ⑤) 모두 `user_cycle_settings.timezone` 을 넘긴다. 구현은 바꾸지 않았다.

### 3-9-5. 자동확정 5중 게이트 (스캔 ②)

```
draft + auto_confirm_at 도달
 ├─ ⓪ 이 사이클에 이미 confirmed 주문 있음?   예 → 조용히 스킵 (멱등. 알림 금지)
 ├─ ① 사용자 auto_confirm = true?             아니오 → awaiting_user (blockedReason=AUTO_CONFIRM_OFF)
 ├─ ② 국가 = US?                              예    → awaiting_user (US_NO_PRICE — 추정가 0 이라 자동확정 근거 부재)
 ├─ ③ 대상 스토어 status='connected'?          아니오 → awaiting_user (STORE_DISCONNECTED)
 ├─ 서버가 최신 식단·냉장고·시세로 확정 스냅샷을 1회 재계산 (아직 상태 전이·inbound 없음)
 ├─ ④ 재계산 미매칭 비율 ≤ 임계(기본 30%)?       아니오 → awaiting_user (UNMATCHED_RATIO)
 ├─ ⑤ 재계산 estimatedTotal ≤ cycle_limit?     아니오 → budget_plans.locked=true  → awaiting_user (BUDGET_EXCEEDED)
 │                                                    locked=false → 경고만 남기고 통과
 ├─ ⑥ 최신 식단 status='over_budget'?          예 → awaiting_user (MEALPLAN_OVER_BUDGET)
 └─ 전부 통과 → 위 재계산 스냅샷으로 status='confirmed', auto_confirmed=true, delivery_eta 설정, auto_confirm_at=NULL
```

- ④·⑤는 **초안에 저장된 과거 라인·금액이 아닌, 바로 확정에 쓸 재계산 스냅샷**을 같이 판정한다. 재계산가가 잠금 한도를 넘으면 확정 전이를 수행하지 않고, 최신 스냅샷만 저장한 뒤 `awaiting_user/BUDGET_EXCEEDED`로 전이한다. 따라서 확정 이후 inbound 단계를 되돌리는 보상 처리가 필요 없다.
- `awaiting_user` 전이 시 `auto_confirm_at = NULL` 로 지워 **스캔 ②가 같은 초안을 반복 판정하지 않게** 한다. 재알림은 사이클당 최대 1회 추가(알림 피로 방지) — `orders.reminded_at` 으로 판정.
- **CWE-367 (TOCTOU)**: 게이트 판정과 저장 사이에 사용자가 수동 승인할 수 있다. 게이트 통과만으로 안전하다고 가정하지 않으며, **부분 유니크 인덱스가 최종 방어선**이다. `IntegrityError` 는 정상 스킵으로 처리하고 에러 알림을 보내지 않는다.
- 다음 사이클 D−5 에 도달했는데 아직 `draft`/`awaiting_user` 인 초안은 `status='expired'` 로 만료시키고 새 초안으로 대체한다 (오래된 초안의 뒤늦은 확정 차단).

### 3-9-6. 멱등성 4중 (FR-816 — 자동화의 전제 조건)

| # | 지점 | 장치 | 위반 시 |
|---|------|------|---------|
| 1 | 자동 식단 생성 (사용자당 주 1회) | `user_cycle_settings.last_generated_cycle_start = cycle_start` 비교. **접수 시점(processing 행 생성 시)에 즉시 기록** — 완료 시점에 기록하면 재시도 폭주 | 스킵 |
| 2 | 초안 (사이클당 1건) | 부분 유니크 `uq_orders_open_cycle (user_id, cycle_start) WHERE status IN ('draft','awaiting_user')` | 기존 초안 재사용 |
| 3 | 확정 (사이클당 1건) | 부분 유니크 `uq_orders_confirmed_cycle (user_id, cycle_start) WHERE status='confirmed'` | `IntegrityError` → 정상 스킵 |
| 4 | 냉장고 등록 (주문당 1회) | **compare-and-set**: `UPDATE orders SET inbound_at=now() WHERE id=:id AND inbound_at IS NULL RETURNING id` — 행이 반환될 때만 `fridge.add_items` 실행. 같은 트랜잭션이므로 등록 실패 시 `inbound_at` 도 롤백되어 다음 스캔에서 재시도 | 스킵 (냉장고 인플레 없음) |

> 사람이 두 번 누르는 것은 실수지만 스케줄러가 두 번 도는 것은 재해다. **4번의 순서(먼저 마킹 → 그 다음 냉장고 쓰기, 한 트랜잭션)** 를 뒤집지 말 것 — 냉장고를 먼저 쓰고 마킹하면 그 사이의 크래시가 곧 인플레다.

### 3-9-7. 정책 파라미터 저장소 — 환경변수 (인계사항 4)

**결정: `pydantic Settings`(환경변수) 를 정본으로 하고, 설정 테이블을 만들지 않는다.**

| 근거 | 내용 |
|------|------|
| **편집 수단 부재** | 현재 제품에 **관리자 인증·관리자 UI 가 없다**. 설정 테이블을 만들어도 편집은 결국 psql 직접 UPDATE 이며, 이는 `.env` 수정보다 위험하고 추적도 안 된다 |
| **요구 충족** | 기획 제약 8의 요구는 "코드 상수가 아닌 조정 가능한 설정"이다. `.env` + 재기동으로 **재배포 없이** 조정되므로 요구를 충족한다 |
| **비용** | 설정 테이블은 CRUD API + 권한 + 캐시 무효화 + 값 검증을 동반한다. 파라미터 15개에 그 값을 치르지 않는다 |
| **경계** | **전역 정책 = 환경변수 / 사용자 정책 = `user_cycle_settings` 컬럼**. 이 경계를 지키면 어디를 봐야 할지가 항상 명확하다 |

**후속 확장점**: 관리자 인증 도입 시 `policy_settings` 테이블로 승격하되, **env 를 기본값 / DB 를 오버라이드**로 읽는 2계층으로 만든다(env 를 버리지 않는다). 그 전까지 승격 금지.

| 키 | 기본값 | 용도 |
|----|--------|------|
| `CYCLE_SCHEDULER_ENABLED` | `true` | 사이클 스케줄러 기동 (**멀티 인스턴스 시 1대만 true**) |
| `CYCLE_SCHEDULER_INTERVAL_SECONDS` | `60.0` | 폴링 주기 |
| `CYCLE_PROFILE_WEEKLY` | `{"generateLeadDays":5,"draftLeadDays":2,"graceHours":24}` | 주 1회 프로파일 |
| `CYCLE_PROFILE_BIWEEKLY` | `{"generateLeadDays":2,"draftLeadDays":1,"graceHours":12}` | 주 2회 프로파일 |
| `CYCLE_STAGE_LOCAL_HOUR` | `9` | 단계 실행 로컬 시각(시) |
| `CYCLE_JITTER_MINUTES` | `30` | 사용자별 결정적 지터 폭 |
| `CYCLE_ACTIVE_COMPLETION_MIN` | `1` | 활성 판정 — 지난 사이클 식사 완료 최소 건수 |
| `CYCLE_ACTIVE_SEEN_DAYS` | `14` | 활성 판정 — 최근 접속 일수 |
| `CYCLE_DAILY_GENERATION_LIMIT` | `200` | **전체** 일일 자동 생성 상한 (FR-817②) |
| `CYCLE_UNMATCHED_THRESHOLD` | `0.30` | 미매칭 비율 임계 (FR-813) |
| `CYCLE_DELIVERY_LEAD_DAYS` | `{"kurly":1,"coupang":1,"ssg":1,"naver":2,"walmart":2,"instacart":1}` | 스토어별 배송 리드타임(일). 미정의 스토어는 `CYCLE_DELIVERY_LEAD_DAYS_DEFAULT` |
| `CYCLE_DELIVERY_LEAD_DAYS_DEFAULT` | `1` | 리드타임 기본값 (JSON 파싱 실패 시 폴백 + 경고 로그) |
| `CYCLE_EXPIRING_DAYS` | `{"KR":3,"US":5}` | 국가별 임박 판정 일수 (FR-806 — US 는 주 1회 대량 배송 전제로 길게) |
| `CYCLE_FRIDGE_PROMPT_MAX_EXPIRING_LINES` | `15` | 프롬프트 임박 재고 최대 줄 |
| `CYCLE_FRIDGE_PROMPT_MAX_LINES` | `25` | 프롬프트 일반 재고 최대 줄 |
| `CYCLE_DRAFT_RETRY_DELAYS_MINUTES` | `1,5,15` | 초안 생성 지수 백오프 |
| `CYCLE_CANCEL_WINDOW_DAYS` | `7` | 확정 취소 허용 기간 (`cycle_start` 기준) |
| `CYCLE_DELIVERY_UNKNOWN_ATTEMPTS` | `3` | "아직 안 왔어요" 누적 횟수 → `delivery_state='unknown'` |

- 파싱 실패(잘못된 JSON, 범위 밖 값)는 **예외로 앱을 죽이지 않고** 기본값으로 폴백 + 경고 로그를 남긴다. 스케줄러가 설정 오타로 멈추는 것이 더 나쁘다.
- 시크릿이 아니므로 `.env.example` 에 전 키를 기본값과 함께 커밋한다 (`.env.example` 갱신은 인프라 에이전트).

### 3-9-8. 냉장고 → 식단 되먹임 (FR-805/806 — 사업계획서 축2 미이행분 해소)

**위치**: `mealplan/service._generate_within_budget` 이 프롬프트 힌트를 만들고, `generator.generate_meals(..., fridge_hint: str = "")` → `_prompt()` 에 전달한다. 시그니처는 기존 `budget_hint` 와 같은 방식으로 **문자열 힌트 1개만** 추가한다(제너레이터는 DB 를 모르는 순수 함수로 유지).

**자동 사이클 전용이 아니다.** `_generate_within_budget` 에 넣으므로 수동 생성·재생성·월간까지 **모든 생성 경로**가 되먹임을 받는다 — 축2 이행이 목적이므로 자동화 여부와 무관해야 한다.

**힌트 조립 규칙** (`_fridge_hint(db, user_id, country)`)

1. `fridge_items` 를 `user_id` 로 조회하고 **`(name.strip().lower(), unit)` 로 합산**한다. `add_items` 는 병합 없이 새 행을 추가하므로 합산이 필수다.
2. 임박 집합 = `expires_at IS NOT NULL AND expires_at <= today + CYCLE_EXPIRING_DAYS[country]`. 정렬은 기존 `_by_expiry`(임박 오름차순, NULL 뒤, 동률 시 created_at).
3. 임박 목록 최대 `CYCLE_FRIDGE_PROMPT_MAX_EXPIRING_LINES`(15)줄, 나머지 재고 최대 `CYCLE_FRIDGE_PROMPT_MAX_LINES`(25)줄. 절삭되면 마지막에 `- ...and N more items` 를 붙여 **"재고가 더 있다"는 사실 자체는 전달**한다.
4. 두 목록이 모두 비면 **섹션 자체를 생략**한다 (빈 섹션은 LLM 을 혼란시킨다).
5. 수량은 `_qstr`(소수 0 제거) 사용. 유통기한은 임박 목록에만 `(expires YYYY-MM-DD)` 로 표기.

**토큰 예산**: 최대 40줄 × 약 12토큰 ≈ **500토큰**. 기존 프롬프트(약 12줄 + 재시도 힌트)에 더해도 요청당 1K 토큰 미만이며, 사용자당 주 1회 자동 생성 상한(FR-817①) 안에서 비용 영향은 무시할 수준이다. 40줄 상한은 정책 파라미터로 조정 가능하다.

**프롬프트 삽입 형태** (system 프롬프트는 건드리지 않는다)

```
Fridge inventory (already owned — prefer recipes that consume these):
- 계란 6 ea
- 두부 2 ea
- ...and 12 more items
Use these FIRST (expiring soon):
- 애호박 1 ea (expires 2026-09-01)
RULES:
- Do NOT reduce ingredient quantities because an item is in the fridge.
  Always list the FULL amount the recipe needs; the server subtracts stock separately.
- Allergy constraints override the fridge. Never use a fridge item that is an allergen.
```

> **두 번째 규칙이 이 설계에서 가장 중요하다.** 감산(`compute_shortfall`)은 **서버가** 식단 재료 총량에서 냉장고 재고를 빼는 방식으로 수행된다. LLM 이 프롬프트를 보고 미리 수량을 줄이면 **이중 감산**이 되어 실제로 필요한 재료를 사지 않게 된다.

**LLM 비활성(mock 폴백) 시**: `_mock()` 은 고정 레시피 뱅크라 되먹임이 적용되지 않는다. 이는 알려진 한계이며, 폴백 경로에서는 `notes` 에 사유를 남기지 않는다(사용자에게 노출할 정보가 아님).

### 3-9-9. 배송 → 냉장고 등록 흐름 (인계사항 1·2)

```
[확정 시점]  order.status='confirmed'
             delivery_eta = (사용자 로컬 confirmed_at 날짜 + lead_days(store)) 의 CYCLE_STAGE_LOCAL_HOUR:00 로컬 → UTC
                            단 delivery_eta < confirmed_at + 1h 이면 confirmed_at + 1h 로 보정
             ※ auto-order-p0 의 "확정 즉시 fridge inbound"(FR-708) 동작을 여기서 제거한다
[delivery_eta 도달]  스캔 ③ → compare-and-set(inbound_at) → line_type='needed' 라인만
                     fridge.add_items(source='delivery', order_id=<주문 id>, expires_at=NULL)
                     → fridge_inbound 알림 "받으셨나요? 냉장고에 담아둘게요"
[사용자 보정]  POST /orders/{id}/delivery {received:false} → order_id 로 등록분 롤백 + eta +1일 + attempts++
               attempts ≥ 3 → delivery_state='unknown' → 자동 등록 중단(스캔 ③ 제외). 사용자가 received:true 를 눌러야 등록
```

- **`source` 값 통합 → `'delivery'` (인계사항 2)**: 배송 시점 등록이므로 의미상 `delivery` 가 맞고, `fridge/schemas.py` 의 Literal 에 정의만 되어 있고 쓰이지 않던 값이 여기서 처음 실사용된다. auto-order-p0 가 도입한 `'order'` 는 **폐기**하고 마이그레이션에서 기존 행을 `delivery` 로 정정한다(db-schema 2-11). Literal 은 `manual | delivery | mealplan` 로 되돌린다 — 값을 둘 다 두면 "같은 것을 가리키는 두 이름"이 영구히 남는다.
- **`fridge_items.order_id` 신설**: FR-815 롤백("해당 주문으로 등록된 항목만")과 배송 미도착 롤백을 **이름·수량 매칭이 아니라 FK 로** 정확히 수행하기 위한 설계 추가분이다. 이름 매칭 롤백은 사용자가 수량을 수정했거나 동명 재료가 섞이면 즉시 틀린다.
- **롤백 규칙**: `fridge_items WHERE order_id=:id` 중 **남아 있는 행만** 삭제한다. 이미 식사 완료로 차감된 분은 되돌리지 않는다(음수 재고 금지). 부분 소진된 행은 남은 수량째로 삭제된다.
- **유통기한**: 실배송 정보가 없으므로 `expires_at=NULL`. 임의 추정 금지 (사용자 보정 전까지 임박 판정 대상 아님).
- `covered` 라인은 등록하지 않는다(이미 냉장고에 있는 재고이므로 등록하면 이중 계상).

### 3-9-10. 비용 상한 구현 지점 (FR-817)

| 상한 | 구현 지점 | 판정 |
|------|-----------|------|
| **사용자당 주 1회** | `cycle/service.py` 생성 단계 진입 조건 | `settings.last_generated_cycle_start != cycle_start` 일 때만 실행. 접수 즉시 기록 |
| **전체 일일 상한** | `cycle/scheduler.py` tick 시작 시 1회 집계 | `SELECT count(*) FROM user_cycle_settings WHERE last_generated_at >= (UTC 오늘 00:00)`. 도달 시 이후 사용자는 `last_stage='deferred_quota'`, `next_run_at=익일 동일 로컬시각`. **실패가 아니다** — 사용자 화면에는 "곧 준비할게요" |
| **수동 생성** | 기존 `mealplan_user_limiter` 5회/분 | 자동 상한과 **무관**. 사용자가 자기 의지로 누르는 것은 막지 않으며, 자동 일일 카운터에도 집계하지 않는다 |

- 일일 상한 판정을 UTC 일 기준으로 단순화한다(사용자 로컬 일 기준으로 하면 전 세계 사용자 집계가 불가능). 문서화된 의도적 단순화.
- **이 방어선은 임의 제거 금지.** LLM 비용이 자동화의 유일한 실질 제약이다.

### 3-9-11. 활성 판정 (FR-802) 과 `users.last_seen_at`

```
활성 =  지난 사이클 [prev_cycle_start, cycle_start) 구간의 meals.completed_at 건수 ≥ CYCLE_ACTIVE_COMPLETION_MIN
    AND users.last_seen_at >= now − CYCLE_ACTIVE_SEEN_DAYS
```

- **`users.last_seen_at timestamptz NULL` 을 신설한다 (설계 추가분).** 현재 스키마에 "최근 접속" 신호가 없다. `refresh_tokens.created_at` 으로 대용할 수 있으나, 로그인 후 방문하지 않아도 최대 14일간 활성으로 오판되어 비용 방어선이 무력해진다.
- 갱신 지점은 **기존 인증 쓰기 경로 3곳만** — ① OAuth 콜백 로그인 ② `POST /auth/refresh`(회전) ③ `GET /auth/app/session`(앱 코드 교환). 읽기 요청마다 UPDATE 하지 않는다. Access 30분 만료이므로 활성 사용자는 약 30분 해상도로 갱신된다.
- **신규 사용자는 자동 생성 대상이 아니다** — "지난 사이클 완료 1건 이상"을 만족할 수 없으므로 자연히 걸러진다. 첫 식단은 홈의 명시 CTA(FR-202)가 만든다. 특례 코드를 두지 않는다.
- 활성 판정 탈락 시 `dormant_since` 를 기록하고 `cycle_paused` 알림을 **1회만** 보낸다. 이후 추가 알림 없음.
- **휴면 복귀(FR-818)**: 복귀 시 밀린 알림·주문을 소급 발송하지 않는다. 홈이 `GET /cycle` 의 `stage='skipped_dormant'` 를 보고 "이번 주 식단 만들까요?" 카드를 **그 사이클에 1회만** 노출한다(닫으면 localStorage 로 그 `cycleStart` 동안 억제 — 서버 상태 아님). 수락 시 기존 `POST /mealplans` 를 호출하고, 그 결과로 식사 완료가 쌓이면 다음 사이클부터 자동 대상이 된다.

### 3-9-12. 관측성

- 사이클 단계 전이와 스킵 사유를 **구조화 로그**로 남긴다: `stage`, `reason`(`skipped_dormant`/`deferred_quota`/`skipped_user`/`awaiting_user`/`expired`/`idempotent_skip`), `cycle_start`, `user_id`.
- **금액·개인정보(가구 구성·재료명·예산액)는 로그에 남기지 않는다** (CWE-359/532). `user_id`(uuid)는 남긴다.

## 4. 환경 변수 (.env — 인프라 에이전트가 .env.example 관리)

| 키 | 위치 | 용도 |
|----|------|------|
| `DATABASE_URL` | backend | postgresql+asyncpg 접속 |
| `JWT_SECRET` / `JWT_ALG=HS256` | backend | JWT·state 서명 |
| `KAKAO_CLIENT_ID/SECRET`, `GOOGLE_CLIENT_ID/SECRET`, (P1) `APPLE_*` | backend | OAuth |
| `FRONTEND_ORIGIN` | backend | Origin 검증·리다이렉트 베이스 |
| `BACKEND_URL` | frontend | rewrites 대상 |


- **주간 자동 사이클(v1.8)**: `CYCLE_*` 정책 파라미터 전체는 **3-9-7 표**가 정본이다. 전 키가 시크릿이 아니므로 기본값과 함께 `.env.example` 에 커밋한다(인프라 에이전트).
  특히 `CYCLE_SCHEDULER_ENABLED` 는 **인스턴스 1대만 true** 로 두어야 한다(3-9-3 멀티 인스턴스 경고).

## 5. 선행/후속 의존성
- **선행**: docker-compose(postgres) + Alembic 초기 리비전 — `/인프라시작` (GATE 3)
- **후속 확장점**: 홈 셸의 데이터 주입 인터페이스(게스트 샘플 ↔ 회원 실데이터), budget_plans 확장(budget 본설계), 애플 어댑터(P1), store 어댑터(마트 연동 기획 시), rate limit 인메모리 → Redis 교체(멀티 인스턴스 배포 시)
- **글로벌-지역전환(v1.5) 이관 항목**: IP·GPS 자동 지역 감지, 기존 데이터 통화 소급 변환, **US Walmart/Instacart 실 API 어댑터**(이번 범위는 국가별 목록·연동 상태·enum 확장까지 — 실연동은 store 본설계). 다국가 확장(현재 KR/US 2국)
- **자동주문 P0(v1.6) 이관 항목**: **US 시세 어댑터**(Walmart/Instacart 파트너 키, P2), **실 체크아웃·자동결제**(P2), **스케줄러/주 2회 주기 UI**(P1). P0 는 시뮬레이션 확정만. 재확정 멱등 키는 P1. 쿠팡/SSG/네이버 전용 검색 어댑터는 만들지 않음

## 변경 이력
- 2026-09-05: **v1.10** — GATE 4 BUG-001 정정. 3-9-5 자동확정의 미매칭·예산 게이트를 초안 스냅샷이 아닌 확정 직전 재계산 스냅샷 기준으로 이동. 잠금 한도 초과 시 확정·inbound 전에 `awaiting_user/BUDGET_EXCEEDED`로 차단
- 2026-08-15: **v1.6** — 자동주문 P0 흐름(3-6) + order 도메인 폴더. 실결제 없이 preview→명시 확정→fridge inbound `source=order`. 설계 토론 5라운드 합의. 미결 0건
- **주간 자동 사이클(v1.8) 이관 항목**: 멀티 인스턴스 스케줄러 분산 락·리더 선출(배포 형상 변경 시 설계 재소집), 실결제 자동확정(별도 명시 동의·1회 상한액·취소 유예·재시도 정책이 선행 조건), 품절 시 대체 재료 자동 제안(알레르기 재검증 필요 — P2), 스토어 배송 상태 웹훅(현 `delivery_eta` 추정은 폴백으로 존치), 정책 파라미터의 `policy_settings` 테이블 승격(관리자 인증 도입 후, env=기본값·DB=오버라이드 2계층)
- 2026-09-04: **v1.9** — 3-9-4 `cycle_limit` 수식 ↔ 구현 대조 완료(일치). 시그니처에 `timezone_name` 표기 보정, 예산안 부재 시 409 와 `GET /cycle` 우회 경로 주석 추가. 변경 이력 2개 절을 하나로 병합(내용 변경 없음)
- 2026-08-30: **v1.8** — 주간 자동 사이클(3-9): 신규 `cycle` 도메인·단방향 의존, lifespan asyncio 스케줄러 3스캔(신규 인프라 없음·단일 인스턴스 경고), `_prorate`→budget 도메인 안분기, 자동확정 5중 게이트, 멱등 4중, 정책 파라미터=환경변수 확정, 냉장고→식단 되먹임 프롬프트 규약, 비용 상한, `users.last_seen_at` 활성 판정. 설계 토론 5라운드 합의
- 2026-09-04: **v1.8 정정** — `cycle_limit`의 안분액과 확정액을 월초부터 이번 사이클 종료까지의 동일 누적 구간으로 맞춰 2회차 이후 한도 붕괴를 수정
- 2026-07-09: 최초 작성 (설계 토론 5라운드 합의)
- 2026-07-09: v1.1 — 회원 홈 흐름(3-4) 추가
- 2026-07-10: v1.5 — 지역 전환 흐름(3-5) + 후속 이관 항목(자동 감지·소급 변환·US 실 API) 명시
