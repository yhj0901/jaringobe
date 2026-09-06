# DB 스키마 가이드

> 원본: `docs/설계/db-schema.md` (v1.9). DDL 은 **인프라 에이전트 전담**, `backend/alembic/` 단일 경로. 기준 시점: v0.2.0 — `alembic heads` = **`0012`** (단일).

## 리비전 체인 (`backend/alembic/versions/`)

```
0001_initial_auth_budget  users · auth_identities · refresh_tokens · budget_plans
0002_mealplan             meal_plans · meals · (재료 등 4테이블)
0003_fridge               fridge_items
0004_household_budget_ext household_members + budget_plans locked/cuisines
0005_store_connections    store_connections
0006_meal_completion      meals.completed_at/time_minutes/difficulty
0007_meal_fridge_deducted meals.fridge_deducted jsonb
0008_store_connections_global  store CHECK + walmart/instacart
0009_orders               orders · order_items                         ← 자동주문 P0 (v1.6)
0010_notification_app     device_tokens · notification_settings · notification_logs · app_login_codes  ← 앱 웹뷰·푸시
0011_cycle_core           user_cycle_settings + orders 확장 + ★백필 + 부분 유니크   ← 주간 사이클 (v1.8)
0012_cycle_links          fridge_items.order_id · source 통합 · users.last_seen_at · notification type CHECK
```

## ERD 요약 (v0.2.0)

```
users 1─N auth_identities        UNIQUE(provider, provider_user_id)
users 1─N refresh_tokens         token_hash SHA-256
users 1─1 budget_plans           locked(예산 락) · currency
users 1─N household_members
users 1─N meal_plans 1─N meals   meals.completed_at / fridge_deducted
users 1─N fridge_items           source ∈ manual|delivery|mealplan, order_id → orders (SET NULL)
users 1─N store_connections      UNIQUE(user_id, store)
users 1─N orders 1─N order_items orders.cycle_start = 멱등 키
users 1─1 user_cycle_settings    UNIQUE(user_id)
users 1─N device_tokens          UNIQUE(token)
users 1─N notification_settings  UNIQUE(user_id, type)
users 1─N notification_logs      template_key 만(본문 원문 없음)
users 1─N app_login_codes        code_hash SHA-256, 60초
```

## 전역 규칙 (모든 신규 테이블 적용)
- PK `uuid` + `gen_random_uuid()` (pgcrypto)
- 시각은 `timestamptz` **UTC** — `timestamp without time zone` 금지. 로컬 날짜가 의미를 갖는 컬럼(`orders.cycle_start`, `user_cycle_settings.skip_until`)만 `date`
- 금액은 `numeric` + `char(3)` 통화 코드 쌍 — float/real 금지
- 열거값은 CHECK 제약 (`ck_{테이블}_{컬럼}`), 인덱스 `ix_`, 유니크 `uq_`. 값이 자주 늘어날 열거(`orders.blocked_reason`, `fridge_items.source`)는 CHECK 없이 애플리케이션 검증
- users 삭제 시 하위 테이블 CASCADE (`fridge_items.order_id` 만 SET NULL — 사용자가 실제로 가진 재료라 주문 이력이 사라져도 남긴다)
- 자격증명 컬럼 금지 (`orders`·`user_cycle_settings`·`device_tokens` 전부 확인)

## 이번 범위 주요 테이블

### `orders` (0009 + 0011 확장) — 자동주문 + 사이클 상태 머신
| 컬럼 | 타입 | 비고 |
|------|------|------|
| `status` | varchar(20) CHECK | `draft`·`awaiting_user`·`confirmed`·`cancelled`·`expired`·`failed` (0009 는 `confirmed` 단일) |
| `frequency` | varchar(20) CHECK | `weekly`·`biweekly` |
| `store` | varchar(10) CHECK | kurly·coupang·ssg·naver·walmart·instacart |
| `estimated_total` / `currency` | numeric(12,2) / char(3) | KRW·USD |
| `simulation` | bool DEFAULT true | 실결제 없음 |
| `confirmed_at` | timestamptz **NULL** | 0011 에서 NOT NULL 해제 — 초안은 확정 시각이 없다 |
| `cycle_start` | date NOT NULL | 배송 기준일(로컬). **멱등 키**. 0011 백필: `(confirmed_at AT TIME ZONE 'Asia/Seoul')::date` |
| `delivery_eta` / `inbound_at` | timestamptz NULL | 배송 예정 / 냉장고 등록 완료(compare-and-set 대상) |
| `auto_confirm_at` / `auto_confirmed` | timestamptz NULL / bool | 그레이스 자동확정 예정(NULL = 안 함) / 자동확정 여부 |
| `delivery_state` | varchar(20) CHECK DEFAULT 'pending' | `pending`·`delivered`·`unknown` — `status` 와 **별도 축** |
| `delivery_confirm_attempts` | smallint DEFAULT 0 | "아직 안 왔어요" 누적 |
| `blocked_reason` | varchar(30) NULL | `awaiting_user` 사유 코드(CHECK 없음) |
| `reminded_at` | timestamptz NULL | 재알림 1회 판정 |
| `meal_plan_id` | uuid FK SET NULL | |

인덱스: `ix_orders_user_created (user_id, created_at DESC)` · **`uq_orders_confirmed_cycle (user_id, cycle_start) WHERE status='confirmed'`**(이중 확정 DB 차단, TOCTOU 최종 방어선) · **`uq_orders_open_cycle (user_id, cycle_start) WHERE status IN ('draft','awaiting_user')`** · `ix_orders_inbound_due (delivery_eta) WHERE status='confirmed' AND inbound_at IS NULL AND delivery_state <> 'unknown'` · `ix_orders_autoconfirm_due (auto_confirm_at) WHERE status='draft' AND auto_confirm_at IS NOT NULL`

`order_items`: `name`·`quantity numeric(10,3)`·`unit`·`line_type(needed|covered)`·`matched`·`title`·`unit_price`·`currency`·`mall_name`·`link`(https 만). **`from_fridge` 컬럼 없음** → 저장 초안 조회 시 부분 충당분 표시 결손(BUG-006, 리비전 0013 후속).

### `user_cycle_settings` (0011)
| 컬럼 | 타입 | 비고 |
|------|------|------|
| `user_id` | uuid UNIQUE FK CASCADE | 사용자당 1행. **lazy 생성이 정본, 마이그레이션 백필 없음** |
| `enabled` | bool DEFAULT true | 일시정지 = false |
| `frequency` | CHECK weekly·biweekly | |
| `anchor_weekday` | smallint CHECK 0~6 | 0=일 … 6=토 (JS `getDay()` 규약) |
| `timezone` | varchar(40) DEFAULT 'Asia/Seoul' | IANA, 앱 검증 |
| `auto_confirm` | bool DEFAULT true | |
| `skip_until` | date NULL | 건너뛴 `cycle_start` |
| `next_run_at` | timestamptz NULL | 스캔 ① 키 |
| `last_stage` | varchar(20) CHECK | `generated`·`generate_failed`·`drafted`·`skipped_dormant`·`skipped_user`·`deferred_quota` |
| `stage_attempts` | smallint | 초안 백오프 횟수 |
| `last_generated_cycle_start` / `last_generated_at` | date / timestamptz | 사용자당 1회 멱등 키 / 일일 상한 집계 |
| `dormant_since` | timestamptz NULL | `cycle_paused` 1회 판정 |

인덱스: `ix_cycle_settings_due (next_run_at) WHERE enabled AND next_run_at IS NOT NULL` (partial — `ix_notification_settings_due` 와 동일 패턴).

### 0012 연결
- `fridge_items.order_id uuid NULL` FK → orders **ON DELETE SET NULL**, `ix_fridge_items_order_id … WHERE order_id IS NOT NULL`. 배송 롤백은 이름 매칭이 아니라 이 FK 기준
- `fridge_items.source`: `'order'` → `'delivery'` 데이터 UPDATE(CHECK 없음). Pydantic Literal 은 `manual | delivery | mealplan`
- `users.last_seen_at timestamptz NULL` (백필 `:= updated_at`). 활성 판정용 단일 타임스탬프 — 접속 이력 누적 아님
- `notification_settings.type` CHECK 재정의: 기존 5종 + `order_approval`·`fridge_inbound`·`cycle_paused`

### 0010 notification
`device_tokens`(platform ios|android, token UNIQUE, locale, timezone) · `notification_settings`(type CHECK, enabled, local_time, timezone, next_send_at + `ix_notification_settings_due` partial) · `notification_logs`(template_key, status sent|failed, `ix_notification_logs_user_sent`) · `app_login_codes`(code_hash char(64) UNIQUE, expires_at, used_at)

## 마이그레이션 절차
```bash
cd backend
uv run alembic upgrade head        # 적용 (컨테이너 진입점이 기동 시 자동 실행, RUN_MIGRATIONS=false 면 수동)
uv run alembic history
uv run alembic heads               # 0012 단일이어야 함
uv run alembic downgrade -1        # 롤백 — ★ 아래 경고 필독
```
- 새 리비전은 인프라 에이전트가 GATE 3 승인 후 작성 → `git fetch` 후 **모든 원격 브랜치의 versions/** 를 확인해 down_revision 이 최신 head 를 가리키게 → 로컬 docker DB 에서 upgrade→downgrade→upgrade 왕복 검증 → `docs/설계/db-schema.md` 갱신
- SQLAlchemy 모델(`domains/*/models.py`)은 마이그레이션과 1:1 유지 (백엔드 테스트가 `compare_metadata` diff 0건으로 검증)
- pytest 는 `TEST_DATABASE_URL` 의 별도 DB 를 매 테스트 drop/create 한다 — 운영 DB 와 반드시 분리

### ★ 0011 적용 시 반드시 확인 — 백필 누락 = 냉장고 재고 2배
자동주문 P0(0009 계약)는 확정 즉시 냉장고에 넣었다. 0011 은 기존 `confirmed` 행에 `cycle_start`·`delivery_eta`·`inbound_at := confirmed_at`·`delivery_state='delivered'` 를 백필한다. 이 백필이 없으면 스캔 ③(`inbound_at IS NULL AND delivery_eta <= now`)이 이미 등록된 주문을 다시 등록한다. 0011 `upgrade()` 내부 순서(컬럼 추가 → 백필 → `cycle_start` NOT NULL 승격 → 중복 검사·강등 → 부분 유니크 인덱스)를 바꾸지 말 것.

적용 후 검증:
```sql
-- 재등록 스캔 후보 = 0 이어야 정상
SELECT count(*) FROM orders WHERE status='confirmed' AND inbound_at IS NULL AND delivery_eta <= now();
-- 사용자·사이클별 confirmed 중복 = 0 행 (0011 이 최신 1건만 남기고 cancelled 로 강등, 남으면 예외로 중단)
SELECT user_id, cycle_start, count(*) FROM orders WHERE status='confirmed' GROUP BY 1,2 HAVING count(*) > 1;
```
QA M-01~M-06(2026-09-05)에서 실데이터(중복 포함 confirmed 3건, `source='order'` 2행)로 검증 완료.

### ⚠ 0011 / 0012 downgrade 는 파괴적이다 — 운영 DB 에서 함부로 내리지 마라
| 리비전 | downgrade 가 하는 일 | 사전 확인 |
|--------|----------------------|-----------|
| `0011` | `confirmed_at` NOT NULL 복원을 위해 **`status <> 'confirmed' OR confirmed_at IS NULL` 인 주문과 연관 `order_items`(CASCADE) 를 DELETE** — 초안·대기·취소·만료·실패 주문 이력이 사라진다. `confirmed` 이력은 보존. 이어서 사이클 컬럼 9종·인덱스·`user_cycle_settings` drop | `SELECT count(*) FROM orders WHERE status <> 'confirmed' OR confirmed_at IS NULL;` 로 손실 행 수 확인 |
| `0012` | `notification_settings` 에서 `order_approval`·`fridge_inbound`·`cycle_paused` 행 **DELETE**(CHECK 원복 전제), `fridge_items.source` `delivery → order` 역 UPDATE, `users.last_seen_at`·`fridge_items.order_id` drop | 사용자 알림 설정(끈 값 포함)이 기본값으로 돌아감을 인지 |

빈 DB 왕복(0012→0010→0012)은 QA 에서 확인됐다. 데이터가 있는 DB 의 롤백은 백업 후에만.

## 데이터 보관
- `refresh_tokens`: 만료/폐기 후 30일 경과분 배치 삭제 대상 (배치 미구현)
- `orders`: 확정 후 24개월 보관 후 배치 삭제 (기간만 명시, 잡 미구현)
- `notification_logs`: 90일 경과분 배치 삭제 (미구현). 본문 원문은 저장하지 않음
- `app_login_codes`: 60초 만료·단일 사용 — 만료 행 정리 배치 미구현
- 이메일은 null 허용 (카카오 동의 거부) — 전 도메인이 null 전제
- `fridge_items.expires_at` 은 배송 등록 시 NULL(실배송 정보 없음, 임의 추정 금지) — 사용자 보정 전까지 임박 판정 대상 아님

## 후속 (인프라)
- **리비전 0013 후보**: `order_items.from_fridge numeric(10,3) NULL` (BUG-006, 백필 NULL 허용 → 과거 초안은 0 표시)
- 멀티 인스턴스 전환 시 스케줄러 분산 락 설계 재소집(스키마 영향 가능)
