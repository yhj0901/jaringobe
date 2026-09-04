# DB 스키마 설계서 — 초기 리비전 (auth + budget v0)

> DDL 은 인프라 에이전트 전담 (`backend/alembic/` 단일 경로). 본 문서가 마이그레이션의 원본 명세다.
> **GATE 3 대상**: 신규 테이블 4개 — 승인 후 `/인프라시작` 으로 초기 리비전 생성.

## 1. ERD

```
users 1 ──── N auth_identities     (소셜 계정 연결 — 현재는 유저당 1개, N 구조로 확장 대비)
users 1 ──── N refresh_tokens      (기기/세션별 세션)
users 1 ──── 1 budget_plans        (v0: 유저당 활성 예산안 1개 — UNIQUE(user_id))
```

**(v1.6 증분)**
```
users 1 ──── N orders              (시뮬레이션 확정 주문 스냅샷)
orders 1 ──── N order_items        (needed/covered 라인 스냅샷)
```
- meal_plan_id 는 SET NULL — 식단 삭제해도 주문 이력 유지
- 자격증명 컬럼 없음. 게스트 주문 행 없음


- 공통: PK 는 `uuid` (`gen_random_uuid()`), 시각은 전부 `timestamptz` **UTC**
- 기존 테이블 없음(최초 리비전) — 하위 호환성 이슈 없음

## 2. 테이블 정의

### 2-1. `users`
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK, default gen_random_uuid() | |
| nickname | varchar(50) | NOT NULL | 미제공 시 서비스가 기본값 생성 |
| email | varchar(255) | NULL | 카카오 동의 거부 시 null (전 도메인이 null 전제) |
| profile_image_url | text | NULL | |
| locale | varchar(10) | NOT NULL default 'ko' | 가입 시 요청 로캘 |
| country | char(2) | NOT NULL default 'KR' | ISO 3166-1 |
| currency | char(3) | NOT NULL default 'KRW' | ISO 4217 |
| onboarding_completed_at | timestamptz | NULL | null=미완료. 게스트 이전 성공 시에도 세팅 |
| created_at / updated_at | timestamptz | NOT NULL default now() | |

- 인덱스: `ix_users_email (lower(email))` — 동일 이메일 타 provider 안내(FR-004)용 조회. UNIQUE 아님(정책상 중복 허용)
- 탈퇴(soft delete) 컬럼은 회원 탈퇴 기획에서 추가 (현 범위 아님)
- **(v1.5) 지역·통화 허용값**: `country ∈ {KR, US}`, `currency ∈ {KRW, USD}`, `KR↔KRW`·`US↔USD` 로 서버 매핑. **DB CHECK 미추가 — 스키마 변경 없음**(컬럼 재사용). 열거 검증은 API 계층(`PUT /users/me/region`)이 담당 (FR-602)

### 2-2. `auth_identities`
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK→users ON DELETE CASCADE | |
| provider | varchar(20) | NOT NULL, CHECK in ('kakao','google','apple') | |
| provider_user_id | varchar(255) | NOT NULL | provider 측 고유 ID |
| email_at_signup | varchar(255) | NULL | 가입 시점 이메일 스냅샷 (애플 relay 포함) |
| created_at | timestamptz | NOT NULL | |

- 제약/인덱스: **`uq_auth_identities_provider_uid UNIQUE(provider, provider_user_id)`** ← 로그인 조회 커버, `ix_auth_identities_user_id`

### 2-3. `refresh_tokens`
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK→users ON DELETE CASCADE | |
| token_hash | char(64) | NOT NULL UNIQUE | SHA-256 hex — **원문 저장 금지** |
| rotated_from | uuid | NULL, FK→refresh_tokens(id) **ON DELETE SET NULL** | 회전 체인 — 재사용 감지용. SET NULL 은 만료분 배치 삭제 시 체인 FK 위반 방지 (구현 시 확정) |
| expires_at | timestamptz | NOT NULL | 발급 +14일 |
| revoked_at | timestamptz | NULL | 로그아웃/회전/재사용 감지 시 세팅 |
| created_at | timestamptz | NOT NULL | |

- 인덱스: UNIQUE(token_hash) 가 검증 조회 커버, `ix_refresh_tokens_user_id`(전 세션 폐기), `ix_refresh_tokens_expires_at`(만료분 배치 삭제)
- 보관: 만료/폐기 후 30일 경과분 배치 삭제 (감사 여유 기간)

### 2-4. `budget_plans` (v0 — 최소 스키마)
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK→users ON DELETE CASCADE, **UNIQUE** | v0: 유저당 1개 |
| household_size | smallint | NOT NULL, CHECK 1~10 | |
| amount | numeric(12,2) | NOT NULL, CHECK > 0 | **float 금지 원칙** |
| currency | char(3) | NOT NULL, CHECK in ('KRW','USD') | |
| meal_direction | varchar(20) | NOT NULL, CHECK in ('health','diet','hearty','kids') | |
| source | varchar(20) | NOT NULL, CHECK in ('guest','onboarding') | 유입 경로 |
| created_at / updated_at | timestamptz | NOT NULL | |

> **확장 예정 (budget 본설계)**: 예산 기간(월 단위 주기), 예산 락 상태, 소진/절약 집계, household 도메인과의 관계 재정의. v0 필드는 게스트 예산안 스키마와 1:1 — 본설계는 이 테이블을 **확장**하며 컬럼 삭제/타입 변경 시 영향도 분석 필수.

## 2-5. mealplan 도메인 (리비전 0002 — 팀원 구현, 문서 회수)

| 테이블 | 요약 |
|--------|------|
| `meal_plans` | 유저별 식단 플랜 (status ready/over_budget, region, currency, period, 금액 numeric+통화). `ix_meal_plans_user_created(user_id, created_at)` — **latest 조회 커버(추가 인덱스 불필요)** |
| `meals` | 플랜별 끼니 (plan_date, meal_type, recipe_name). `ix_meals_plan_date` |
| `meal_ingredients` | 끼니별 재료 (수량/단위/추정가). `ix_meal_ingredients_meal` |
| `ingredient_price_refs` | 지역별 기준가 테이블. `ix_price_region_name(region, name)` |

- 상세 명세는 리비전 파일(`0002_mealplan.py`)과 models.py 가 원본 — 본 문서는 요약 유지

## 2-6. household + budget 확장 (리비전 0004 — GATE 3 대상)

**`household_members` 신규**
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | uuid | PK gen_random_uuid() |
| user_id | uuid | NOT NULL FK→users ON DELETE CASCADE |
| member_type | varchar(10) | CHECK in ('adult_m','adult_f','teen','child','toddler') |
| age | smallint | CHECK 0~99 (유형-나이 정합은 서비스 검증) |
| position | smallint | NOT NULL (표시 순서) |
| created_at | timestamptz | NOT NULL default now() |
- `ix_household_members_user_id`

**`budget_plans` 확장**: `locked boolean NOT NULL DEFAULT true`, `cuisines jsonb NOT NULL DEFAULT '[]'` (enum 배열은 서비스 검증)

## 2-7. store_connections (리비전 0005 / 0008 국가별 확장 — GATE 3 대상)

| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | uuid | PK |
| user_id | uuid | NOT NULL FK→users CASCADE |
| store | varchar(10) | CHECK in ('kurly','coupang','ssg','naver','walmart','instacart') ← **0008 로 walmart·instacart 편입** |
| status | varchar(15) | CHECK in ('connected','disconnected') |
| connected_at | timestamptz | NULL |
| created_at/updated_at | timestamptz | NOT NULL |
- **UNIQUE(user_id, store)**, `ix_store_connections_user_id`
- 자격증명 컬럼 없음 — 실연동 시 store 본설계에서 암호화 참조로 확장 (평문 저장 금지 원칙)
- **(v1.5) 국가별 세트**: 애플리케이션 계층에서 `user.country` 로 노출 세트 결정(KR 4 / US 2). DB 는 전체 enum 허용, **국가↔스토어 매핑 CHECK 는 두지 않음**(지역 전환 시 타 국가 연동 행 보존·복원 위함). `store` 는 `varchar(10)` 로 `instacart`(9자)·`walmart`(7자) 수용 — **컬럼 타입 변경 불필요**, CHECK 제약만 재정의

## 2-8. orders + order_items (리비전 0009 — GATE 3 대상, v1.6)

자동주문 P0 시뮬레이션 확정 스냅샷. PK uuid + timestamptz UTC. 금액 numeric, float 금지. **자격증명 컬럼 금지** (평문/암호문 모두 — 실연동 시 store 본설계의 암호화 참조를 쓰지, orders 에 복사하지 않음).

**`orders`**

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK, gen_random_uuid() | |
| user_id | uuid | NOT NULL, FK→users CASCADE | |
| meal_plan_id | uuid | NULL, FK→meal_plans **ON DELETE SET NULL** | 스냅샷 시점 식단. 식단 삭제해도 주문 이력 유지 |
| store | varchar(10) | NOT NULL, CHECK in ('kurly','coupang','ssg','naver','walmart','instacart') | 확정 대상 연동 스토어 |
| status | varchar(20) | NOT NULL, CHECK in ('confirmed') | P0 는 confirmed 만. 후속 paid/failed 는 CHECK 확장. **paid 값을 P0 에 두지 않음** (0011 에서 6값으로 확장 — 2-10. `failed` 는 예약 상태, api-spec 10-8) |
| frequency | varchar(20) | NOT NULL DEFAULT 'weekly', CHECK in ('weekly') | P1 에 biweekly 확장 |
| next_suggested_at | timestamptz | NOT NULL | **행 생성 시각 + 7일(weekly) / 3일(biweekly)** — 초안 생성·명시 확정 시 서버가 부여. 표시용, 잡 없음. (v1.9 정정: v1.6 의 "confirmed_at + 7 days" 는 초안에 confirmed_at 이 없어 성립하지 않는다 — `order.service.create_draft`/`confirm_order` 기준) |
| estimated_total | numeric(12,2) | NOT NULL | 시세 없으면 0 |
| currency | char(3) | NOT NULL, CHECK in ('KRW','USD') | |
| simulation | boolean | NOT NULL DEFAULT true | 실결제 도입 전까지 true 고정 |
| confirmed_at | timestamptz | ~~NOT NULL~~ → **NULL** (리비전 **0011** `ALTER COLUMN confirmed_at DROP NOT NULL`) | 0009 시점엔 `confirmed` 단일 상태라 NOT NULL. 0011 이 초안(`draft`/`awaiting_user`)을 같은 테이블에 두면서 NULL 허용 — 확정 전 행은 NULL, 확정 시 `now()`. **v1.9 표기 정정**(v1.8 문서에 누락) |
| created_at / updated_at | timestamptz | NOT NULL default now() | |

- 인덱스: `ix_orders_user_created (user_id, created_at DESC)` — latest 커버
- 보관: 회원 탈퇴 시 users CASCADE 로 주문·라인 삭제. 활성 계정은 **확정 후 24개월** 보관 후 배치 삭제(개인정보 최소화). P0 는 배치 잡 미구현 — 스키마 주석에 기간만 명시
- 게스트 주문 행은 존재하지 않음

**`order_items`**

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| order_id | uuid | NOT NULL, FK→orders CASCADE | |
| name | varchar(200) | NOT NULL | 식단 재료명 스냅샷 |
| quantity | numeric(10,3) | NOT NULL, CHECK > 0 | needed 면 toBuy, covered 면 fromFridge |
| unit | varchar(16) | NOT NULL | |
| line_type | varchar(20) | NOT NULL, CHECK in ('needed','covered') | |
| matched | boolean | NOT NULL DEFAULT false | 스토어 카트 매칭 |
| title | varchar(500) | NULL | 매칭 상품명 |
| unit_price | numeric(12,2) | NULL | 매칭가. US/키없음 NULL |
| currency | char(3) | NULL | |
| mall_name | varchar(100) | NULL | |
| link | text | NULL | https 만 저장 (그 외 null) |
| created_at | timestamptz | NOT NULL | |

- 인덱스: `ix_order_items_order_id`
- inbound 대상은 `line_type='needed'` 만. covered 라인도 스냅샷(리뷰 재현)하되 fridge inbound 금지

### fridge 영향 (마이그레이션 없음)

- `fridge_items.source` 는 varchar(20), **DB CHECK 없음**. Pydantic Literal 에 `"order"` 추가 (코드만). 기존 값 `manual|delivery|mealplan` 유지
- inbound 는 기존 `add_items` 처럼 **새 행 추가**(병합 없음). `expires_at=null`
- 식사완료 deduct FIFO 는 변경하지 않음 → 주문 inbound 분이 이후 완료 차감에 자연 포함

> **문서 정합 안내(v1.8)**: 아래 2-9~2-13 과 3-B 는 `feature/auto-order-p0`(2-8 `orders`/`order_items`, 리비전 0009) 와 `feature/app-webview-push`(notification 4테이블, 리비전 0008→**0010 리넘버**) 가 main 에 머지된 상태를 전제한다. 두 브랜치가 각각 `2-8` 절 번호를 사용했으므로 머지 시 절 번호 재배정이 필요하다(문서 에이전트 소관).

## 2-9. `user_cycle_settings` (신규 — 리비전 0011, GATE 3 대상, v1.8)

> 기획: `docs/기획/루프완결-주간사이클.md` 9-1. 사용자별 사이클 정책 + 스케줄러 스캔 키.
> **자격증명 컬럼 없음**(CWE-522). 금액 컬럼 없음. `notification_settings` 의 partial index 패턴을 그대로 따른다.

| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK, `gen_random_uuid()` | |
| user_id | uuid | NOT NULL, **UNIQUE**(`uq_cycle_settings_user`), FK→users **CASCADE** | 사용자당 1행 |
| enabled | boolean | NOT NULL DEFAULT true | 사이클 활성 / 일시정지 |
| frequency | varchar(20) | NOT NULL DEFAULT 'weekly', CHECK in ('weekly','biweekly') | 프로파일 선택 |
| anchor_weekday | smallint | NOT NULL DEFAULT 0, CHECK 0~6 | 배송 기준 요일. **0=일요일 … 6=토요일** (JS `getDay()` 규약) |
| timezone | varchar(40) | NOT NULL DEFAULT 'Asia/Seoul' | IANA. 애플리케이션에서 `ZoneInfo` 화이트리스트 검증 (CWE-20) |
| auto_confirm | boolean | NOT NULL DEFAULT true | 그레이스 자동확정 on/off |
| skip_until | date | NULL | "이번 사이클 건너뛰기" 대상 `cycle_start` |
| next_run_at | timestamptz | NULL | 다음 단계 트리거 시각(UTC) — 스케줄러 스캔 ① 키 |
| last_stage | varchar(20) | NULL, CHECK in (아래 목록) | 마지막 완료/판정 단계 |
| stage_attempts | smallint | NOT NULL DEFAULT 0 | 현재 단계 재시도 횟수(초안 백오프·생성 재시도) |
| last_generated_cycle_start | date | NULL | 자동 생성 멱등 키 (사용자당 사이클 1회 — FR-817①) |
| last_generated_at | timestamptz | NULL | 전체 일일 상한 집계용 (FR-817②) |
| dormant_since | timestamptz | NULL | 휴면 전환 시각 (`cycle_paused` 알림 1회 판정) |
| created_at / updated_at | timestamptz | NOT NULL DEFAULT now() | |

- `last_stage` CHECK: `('generated','generate_failed','drafted','skipped_dormant','skipped_user','deferred_quota')`
- 인덱스: `ix_cycle_settings_due` **partial** — `ON (next_run_at) WHERE enabled AND next_run_at IS NOT NULL` (`ix_notification_settings_due` 와 동일 패턴)
- **행 생성 시점 (인계사항 6) — lazy 가 정본, 백필 없음**
  - 마이그레이션에서 **전체 사용자 백필을 하지 않는다.** 백필하면 미온보딩·휴면 사용자까지 스캔 대상이 되고, 이후 기본값을 바꿔도 이미 굳은 행이 남는다.
  - 정본: `get_or_create_settings(db, user)` — `GET /cycle`·`PUT /cycle/settings`·`POST /cycle/skip` 최초 호출 시 기본값으로 생성 (notification 도메인의 lazy 패턴 승계).
  - 보조: **온보딩 완료 처리**(`PUT /households/me` 가 `users.onboarding_completed_at` 을 채우는 지점)에서도 **동일한 idempotent 함수**를 호출한다. 홈을 한 번도 안 열어도 사이클이 시작된다.
  - 생성 시 `next_run_at` = 다음 사이클 D−5 의 로컬 `CYCLE_STAGE_LOCAL_HOUR`:00 + 사용자 지터 → UTC.

## 2-10. `orders` 확장 (리비전 0011 — GATE 3 대상, v1.8)

> 대상: 2-8 의 `orders` (리비전 0009, `feature/auto-order-p0`). **전부 additive 또는 CHECK 확장** — 컬럼 삭제·타입 변경 없음.

| 컬럼 | 변경 | 설명 |
|------|------|------|
| `status` | **CHECK 확장** `('confirmed')` → `('draft','awaiting_user','confirmed','cancelled','expired','failed')` | 상태 머신 (CWE-841). 기존 값 `confirmed` 포함 → 기존 행 영향 없음 |
| `frequency` | **CHECK 확장** `('weekly')` → `('weekly','biweekly')` | FR-814 |
| `confirmed_at` | **NOT NULL → NULL** (`ALTER COLUMN confirmed_at DROP NOT NULL`) | 초안은 확정 시각이 없다(api-spec 10-4). 0011 `upgrade()` 에 구현돼 있으나 v1.8 문서에 누락 — **v1.9 표기 추가**. downgrade 는 NOT NULL 복원 전에 `status <> 'confirmed' OR confirmed_at IS NULL` 행(과 `order_items` CASCADE)을 **삭제**한다 — 파괴적 롤백(아래 리스크 표) |
| `cycle_start` | **신규** `date NOT NULL` | 이 주문이 속한 사이클의 배송 기준일(사용자 로컬 date). **멱등 키** |
| `delivery_eta` | **신규** `timestamptz NULL` | 배송 예정 시각 (인계사항 1). NULL = 아직 확정되지 않은 초안 |
| `inbound_at` | **신규** `timestamptz NULL` | 냉장고 등록 완료 시각 — compare-and-set 대상 (1회 보장) |
| `auto_confirm_at` | **신규** `timestamptz NULL` | 그레이스 자동확정 예정 시각. **NULL = 자동확정 안 함**(설정 off / US / 게이트 차단 후) |
| `auto_confirmed` | **신규** `boolean NOT NULL DEFAULT false` | 사용자 승인과 자동확정을 구분해 기록 |
| `delivery_state` | **신규** `varchar(20) NOT NULL DEFAULT 'pending'`, CHECK in ('pending','delivered','unknown') | 배송 확인 상태. **`status`(주문 생애주기)와 분리** — 상태 머신을 오염시키지 않기 위해 |
| `delivery_confirm_attempts` | **신규** `smallint NOT NULL DEFAULT 0` | "아직 안 왔어요" 누적 (기획 5-3) |
| `blocked_reason` | **신규** `varchar(30) NULL` | `awaiting_user` 사유 코드 (API 가 그대로 내려주고 프론트가 i18n 매핑) |
| `reminded_at` | **신규** `timestamptz NULL` | 승인 재알림 1회 한도 판정 (알림 피로 방지) |

- `blocked_reason` 허용값(애플리케이션 검증, DB CHECK 없음 — 값이 늘어날 여지가 커서 CHECK 를 두면 마이그레이션이 잦아진다):
  `BUDGET_EXCEEDED` · `UNMATCHED_RATIO` · `STORE_DISCONNECTED` · `AUTO_CONFIRM_OFF` · `US_NO_PRICE` · `MEALPLAN_OVER_BUDGET`

**신규 인덱스**

| 이름 | 정의 | 용도 |
|------|------|------|
| `uq_orders_confirmed_cycle` | **UNIQUE** `(user_id, cycle_start) WHERE status='confirmed'` | FR-816 이중 확정 DB 차단 (최종 방어선) |
| `uq_orders_open_cycle` | **UNIQUE** `(user_id, cycle_start) WHERE status IN ('draft','awaiting_user')` | 사이클당 열린 초안 1건 |
| `ix_orders_inbound_due` | `(delivery_eta) WHERE status='confirmed' AND inbound_at IS NULL AND delivery_state <> 'unknown'` | 스케줄러 스캔 ③ |
| `ix_orders_autoconfirm_due` | `(auto_confirm_at) WHERE status='draft' AND auto_confirm_at IS NOT NULL` | 스케줄러 스캔 ② |

- 기존 `ix_orders_user_created` 유지.
- **상태 전이 규칙(애플리케이션 강제, CWE-841)**: `draft → awaiting_user → confirmed → cancelled` / `draft|awaiting_user → expired` / `* → failed`. **`confirmed → draft` 역행 금지**, `inbound_at IS NOT NULL` 인 주문의 재확정 금지. **(v1.9)** `failed` 는 **예약 상태** — v1.9 까지 생산 경로 없음, `failed → *` 전이 없음(터미널). 부분 유니크 인덱스 대상이 아니므로 같은 사이클의 새 초안·재확정을 막지 않는다(api-spec 10-8).

### 기존 행 백필 방침 (인계사항 1 — 순서가 중요)

`feature/auto-order-p0` 는 미머지이므로 **운영 DB(`jaringobe`)에 `orders` 행이 없다**. 아래는 개발 DB(`jaringobe_dev`) 또는 브랜치 머지 후 먼저 쌓인 행을 위한 방침이며, 행이 0건이면 자연히 무해하다.

```
1) 컬럼 추가 (전부 NULL 허용 또는 DEFAULT 있는 상태로)
2) 백필
     cycle_start   := confirmed_at 을 'Asia/Seoul' 로 본 날짜   -- 사용자 타임존 미보유 시점의 기존 행이므로 서버 기본 타임존 사용
     delivery_eta  := confirmed_at                              -- 이미 배송된 것으로 간주
     inbound_at    := confirmed_at        ★ 반드시
     delivery_state:= 'delivered'
     auto_confirmed:= false
3) cycle_start NOT NULL 로 승격
4) 중복 검사 (인덱스 생성 전 필수)
     SELECT user_id, cycle_start, count(*) FROM orders WHERE status='confirmed'
     GROUP BY 1,2 HAVING count(*) > 1;
     → 행이 나오면 최신 1건만 남기고 나머지를 status='cancelled' 로 강등한 뒤 진행 (임의 삭제 금지)
5) 부분 유니크 인덱스 생성 (운영 DB 는 CONCURRENTLY 검토)
```

> **★ `inbound_at := confirmed_at` 이 이 백필의 핵심이다.** auto-order-p0 는 **확정 즉시** 냉장고에 inbound 했다. 새 스캔 ③은 `inbound_at IS NULL` 을 대상으로 하므로, 백필을 빠뜨리면 **이미 냉장고에 들어간 주문이 한 번 더 등록되어 재고가 두 배가 된다.** 이 한 줄이 마이그레이션 전체에서 가장 위험한 항목이다.

## 2-11. `fridge_items` 확장 — `order_id` 신설 + `source` 값 통합 (리비전 0012, v1.8)

| 컬럼 | 변경 | 설명 |
|------|------|------|
| `order_id` | **신규** `uuid NULL`, FK→orders **ON DELETE SET NULL** | 이 재고가 어느 주문의 배송분인지. 주문 취소·배송 미도착 롤백의 정확한 기준 |
| `source` | **값 정리(데이터 UPDATE)** | `'order'` → `'delivery'` 일괄 정정 |

- 인덱스: `ix_fridge_items_order_id (order_id) WHERE order_id IS NOT NULL` — 롤백 조회 커버.
- **`source` 통합 결정 (인계사항 2)**: `fridge_items.source` 는 `varchar(20)` 이며 **DB CHECK 가 없다**. 따라서 값 변경에 제약 재정의는 불필요하고 데이터 UPDATE 1회만 필요하다.
  ```sql
  UPDATE fridge_items SET source = 'delivery' WHERE source = 'order';
  ```
  Pydantic Literal 은 `manual | delivery | mealplan` 로 되돌린다(`order` 제거). 프론트 타입도 동일. **두 값을 병존시키지 않는 이유**: 같은 개념(주문 배송분)을 가리키는 이름이 둘이면 이후 모든 집계·필터가 두 값을 다 알아야 하고, 하나를 빠뜨리는 순간 조용히 틀린다.
- `order_id` 를 쓰는 이유: FR-815 는 "`order_items` 스냅샷 기준 삭제"를 제안했으나, 이름·수량 매칭 롤백은 **사용자가 수량을 보정했거나 동명 재료가 섞이면 즉시 틀린다.** FK 는 틀릴 수 없다.
- 기존 행(`source='manual'|'mealplan'`)은 `order_id=NULL` — 영향 없음.

## 2-12. `users.last_seen_at` 신설 (리비전 0012, v1.8 — 설계 추가분)

| 컬럼 | 변경 | 설명 |
|------|------|------|
| `last_seen_at` | **신규** `timestamptz NULL` | 최근 접속 시각. 활성 판정(FR-802)의 두 조건 중 하나 |

- **추가 근거**: 현재 스키마에 "최근 접속" 신호가 없다. `refresh_tokens.created_at`(최대 14일 유효)으로 대용하면 **로그인 후 방문하지 않아도 활성으로 오판**되어 LLM 비용 방어선이 무력해진다.
- 백필: `last_seen_at := updated_at` (기존 사용자에게 합리적 근사). NULL 이면 애플리케이션이 "비활성"으로 판정한다.
- 갱신 지점은 **기존 인증 쓰기 경로 3곳만** — OAuth 콜백 로그인 / `POST /auth/refresh` / `GET /auth/app/session`. 읽기 요청마다 UPDATE 하지 않는다(쓰기 폭증 방지). Access 30분 만료이므로 활성 사용자는 약 30분 해상도로 갱신된다.
- 인덱스 없음 — 판정은 스캔 ①이 고른 사용자 1명에 대해서만 수행된다.

## 2-13. `notification_settings.type` CHECK 재정의 (리비전 0012, v1.8 — 인계사항 7)

**확인 결과: CHECK 제약이 존재한다 → 마이그레이션 필요하다.**

`0008_notification_app.py` 는 `sa.CheckConstraint(f"type IN ({_SETTING_TYPES})", name="ck_notification_settings_type")` 를 생성하며, 모델 `notification/models.py` 의 `__table_args__` 에도 동일 제약이 있다. 값만 추가하는 것으로는 INSERT 가 거부된다.

```sql
ALTER TABLE notification_settings DROP CONSTRAINT ck_notification_settings_type;
ALTER TABLE notification_settings ADD CONSTRAINT ck_notification_settings_type CHECK (
  type IN ('meal_reminder_breakfast','meal_reminder_lunch','meal_reminder_dinner',
           'mealplan_done','weekly_nudge',
           'order_approval','fridge_inbound','cycle_paused')   -- 신규 3종
);
```

- `type` 은 `varchar(30)` — 신규 값 최장 `order_approval`(14자)·`fridge_inbound`(14자)·`cycle_paused`(12자) 로 **컬럼 폭 변경 불필요**.
- 코드 동기화(같은 커밋에서 함께): `notification/models.py` 의 `SETTING_TYPES` + `CheckConstraint` 문자열, `notification/service.py` 의 `DEFAULT_ENABLED`, `notification/schemas.py` 의 타입 열거, `notification/sender.py` 의 `TEMPLATES`(ko/en 신규 템플릿 3종).
- 신규 3종 기본값은 **enabled=true**(트랜잭션 알림 — 광고성 아님). `local_time`/`timezone`/`next_send_at` 은 NULL (리마인더가 아니므로 `REMINDER_TYPES` 에 넣지 않는다).
- downgrade 는 KR 5종으로 CHECK 원복. **신규 3종 행이 존재하면 실패**하므로 downgrade 에서 해당 행을 먼저 DELETE 한다(문서화).

## 3. 마이그레이션 계획 (인프라 에이전트 실행)

| 리비전 | 내용 | 상태 |
|--------|------|------|
| `0001_initial_auth_budget` | 4테이블 + 인덱스/제약 일괄 생성. `CREATE EXTENSION IF NOT EXISTS pgcrypto` (gen_random_uuid) | **적용·검증 완료** (2026-07-09, 로컬 docker postgres 16 에서 upgrade→downgrade→upgrade 왕복 PASS) |
| `0002_mealplan` | mealplan 4테이블 + 인덱스 (팀원 작성, down_revision=0001) | **적용 완료** (2026-07-09 서버·로컬) |
| `0004_household_budget_ext` | household_members 신규 + budget_plans locked/cuisines (down_revision=0003) | **작성·로컬 왕복 검증 PASS** (2026-07-09, GATE 3 통과) |
| `0005_store_connections` | store_connections 신규 (down_revision=0004) | **작성·로컬 왕복 검증 PASS** (2026-07-10, GATE 3 통과) |
| `0006_meal_completion` | meals 에 completed_at·time_minutes·difficulty(NULL) 3컬럼 (down_revision=0005) | **작성·로컬 왕복 검증 PASS** (2026-07-10, GATE 3 통과) |
| `0007_meal_fridge_deducted` | meals.fridge_deducted jsonb NULL (down_revision=0006). 완료 시 실제 차감 스냅샷 | **main 적용** (2026-08-15, #37) |
| `0008_store_connections_global` | `ck_store_connections_store` 제약 재정의: kurly/coupang/ssg/naver **+ walmart + instacart** (down_revision=**0007**). 기존 행 영향 없음·컬럼 타입 변경 없음. downgrade 는 KR 4종으로 CHECK 원복(US 연동 행 존재 시 실패 가능 — 문서화). 모델 `connection_models.py` CheckConstraint 도 동시 동기화 | **파일 작성 완료**(2026-08-15, #37 머지 후 리비전 재정렬). store 제약 변경 → **팀원 리뷰 필수** |
| `0009_orders` | `orders` + `order_items` 신규 (down_revision=**0008**). PK uuid, 금액 numeric, 자격증명 컬럼 없음. latest 커버 인덱스 `ix_orders_user_created`. fridge.source 는 코드 Literal 만 (`order`) — **DB CHECK/마이그레이션 없음** | **GATE 3 대상** (설계 v1.6). 인프라 에이전트가 작성·왕복 검증 |

> **v1.8 증분(0011·0012)은 아래 3-B 참조** — `feature/auto-order-p0`(0009)·`feature/app-webview-push`(0010 리넘버) 머지 후 인프라가 최종 번호 부여.

- 롤백: 4테이블 역순 drop (최초 리비전이므로 단순, pgcrypto 확장은 유지)
- 파일: `backend/alembic/versions/0001_initial_auth_budget.py`

## 3-B. 마이그레이션 계획 — v1.8 증분 (인계사항 9)

**브랜치 머지 순서 (기획 Q5 확정)**: `feature/auto-order-p0`(0009, `down_revision=0008`) → `feature/app-webview-push`(0008 → **0010 으로 리넘버**, `down_revision=0009`) → **본 설계 0011·0012**.

| 리비전 | down_revision | 내용 | 상태 |
|--------|---------------|------|------|
| `0011_cycle_core` | `0010` | `user_cycle_settings` 신규(+partial index) · `orders` 컬럼 9종 추가 · **`confirmed_at` DROP NOT NULL**(v1.9 표기 추가) · `status`/`frequency` CHECK 확장 · **백필** · 중복 검사 · 부분 유니크 인덱스 2종 · due 인덱스 2종 | **GATE 3 대상** — 인프라 작성·왕복 검증 |
| `0012_cycle_links` | `0011` | `fridge_items.order_id`(+partial index) · `source='order'→'delivery'` UPDATE · `users.last_seen_at`(+백필) · `notification_settings` type CHECK 재정의 | **GATE 3 대상** |

- ~~**리비전 번호는 잠정값**이다.~~ **(v1.9) 0011·0012 로 확정됐다** — `feature/loop-cycle-base` 체인 `0010 → 0011_cycle_core → 0012_cycle_links`. 아래 잠정 문구는 이력으로만 남긴다: 두 선행 브랜치의 머지·리넘버가 끝난 뒤 인프라 에이전트가 최종 번호를 부여한다(CLAUDE.md 협업 규칙 3). 0009/0010 이 밀리면 본 설계는 0012/0013 이 된다.
- **0011 upgrade() 내부 실행 순서를 지킬 것**: 컬럼 추가 → 백필(★`inbound_at`) → `cycle_start` NOT NULL 승격 → 중복 검사 → 부분 유니크 인덱스 생성. 순서를 바꾸면 인덱스 생성이 실패하거나 냉장고 인플레가 발생한다.
- 2개로 나눈 이유: 0011 은 사이클 자체 상태(순서 민감·롤백 시 통째로 되돌려야 함), 0012 는 타 도메인 연결(fridge/auth/notification)로 성격과 리스크가 다르다. 한 리비전에 섞으면 부분 실패 시 downgrade 가 지저분해진다.

### 마이그레이션 리스크

| 항목 | 리스크 | 완화 |
|------|--------|------|
| `orders.status`·`frequency` CHECK 확장 | **낮음** — 기존 값이 새 집합에 포함 | 확장만, 축소 금지 |
| `orders.cycle_start` NOT NULL | **중간** — 백필 필요 | `confirmed_at` 로컬 date 로 백필 후 승격 |
| `orders.confirmed_at` DROP NOT NULL (v1.9 표기 추가) | **낮음(upgrade) / 높음(downgrade)** — upgrade 는 제약 완화만. downgrade 는 초안·대기·취소·만료·실패 주문과 그 `order_items` 를 삭제한 뒤 NOT NULL 을 복원 | 운영 롤백 전 `SELECT count(*) FROM orders WHERE status <> 'confirmed' OR confirmed_at IS NULL` 로 손실 행 수 확인. `confirmed` 이력은 보존된다 |
| **`inbound_at` 백필 누락** | **높음** — 기존 확정 주문이 냉장고에 재등록되어 재고 2배 | 백필 필수. 검증 쿼리: `SELECT count(*) FROM orders WHERE status='confirmed' AND inbound_at IS NULL AND created_at < :migration_ts` = 0 |
| 부분 유니크 인덱스 | **중간** — 백필 결과에 중복이 있으면 생성 실패 | 생성 전 중복 검사 쿼리 선행. 운영 DB 는 `CONCURRENTLY` 검토 |
| `fridge_items.source` UPDATE | **낮음** — CHECK 없음, 행 수 적음 | 단일 UPDATE. downgrade 는 역방향 UPDATE |
| `notification_settings` CHECK 재정의 | **낮음** — 기존 5종 포함 | downgrade 시 신규 3종 행 선삭제 필요 |
| `users.last_seen_at` | **낮음** — additive, NULL 허용 | `updated_at` 백필 |
| partial index 스캔 성능 | **낮음** | `notification_settings` 에서 검증된 패턴 재사용 |
| `user_cycle_settings` 신규 | **낮음** — additive, 백필 없음 | lazy 생성 (2-9) |

**총평**: upgrade 는 파괴적 변경 없음(전부 additive / CHECK 확장 / 제약 완화 / 값 정정). 유일한 고위험 항목은 **`inbound_at` 백필 누락**이며, 이는 스키마가 아니라 데이터 정합 문제다. **(v1.9)** 0011 **downgrade** 는 `confirmed_at` NOT NULL 복원을 위해 비확정 주문을 삭제하는 파괴적 롤백임을 명시한다.

### ERD 증분 (v1.8)

```
users 1 ──── 1 user_cycle_settings   (UNIQUE(user_id) — 사용자당 1행)
orders 1 ──── N fridge_items         (order_id, ON DELETE SET NULL — 배송분 추적·롤백)
```
- `user_cycle_settings` 에 자격증명·금액 컬럼 없음
- `fridge_items.order_id` 는 SET NULL — 주문 이력이 지워져도 냉장고 재고는 남는다(사용자가 실제로 가진 재료이므로)

## 변경 이력
- 2026-09-04: **v1.9** — 구현 정합 표기 정정(DDL 변경 없음). 2-8 `orders.confirmed_at` **NOT NULL → NULL** (리비전 **0011** `DROP NOT NULL`, v1.8 문서 누락분) + `next_suggested_at` 산식 구현 기준 정정, 2-10 에 `confirmed_at` 변경 행·`failed` 예약 상태 명시, 3-B 0011 요약·리비전 번호 확정(0011·0012)·downgrade 파괴성 리스크 행 추가
- 2026-08-15: **v1.6** — 2-8 `orders`+`order_items` (리비전 **0009_orders**, down_revision=**0008**). fridge source `order` 는 코드만. 설계 토론 5라운드 합의
- 2026-08-30: **v1.8** — 주간 자동 사이클: 2-9 `user_cycle_settings` 신규, 2-10 `orders` 확장(컬럼 9종·CHECK 확장·부분 유니크 2종·**`inbound_at` 백필 필수**), 2-11 `fridge_items.order_id` + `source` `order`→`delivery` 통합, 2-12 `users.last_seen_at`, 2-13 `notification_settings` type CHECK **재정의 필요 확인**. 리비전 **0011·0012**(잠정, 브랜치 머지 후 인프라 확정). 설계 토론 5라운드 합의
- 2026-07-10: v1.5 — 2-7 store_connections CHECK 에 walmart·instacart 편입(리비전 0008 계획, GATE 3·팀원 리뷰) + 2-1 users country/currency 허용값(KR/US·KRW/USD, DB CHECK 없음·API 검증) 명시
- 2026-07-09: v1.2 — 2-6 household_members + budget_plans 확장 설계 (리비전 0004 계획)
- 2026-07-09: 최초 작성 — auth 3테이블 + budget_plans v0 (설계 토론 5라운드 합의)
- 2026-07-09: 리비전 0001 작성·로컬 검증 완료 (GATE 3 통과). rotated_from FK 는 ON DELETE SET NULL 로 확정
- 2026-07-09: 0002(mealplan, 팀원) 문서 회수 — 회원홈-식단연결 설계는 DB 변경 없음(기존 인덱스 커버)
