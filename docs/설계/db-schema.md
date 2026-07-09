# DB 스키마 설계 — 예산 락 + AI 식단 자동 생성

> PostgreSQL 16 / SQLAlchemy 2.0(async) / Alembic. 금액 `numeric`, 시각 `timestamptz`(UTC).
> DDL·마이그레이션은 **인프라 에이전트 전담**(GATE 3). 본 문서는 설계 계약.

## ERD (개념)

```
household (auth/household 도메인, 기존 전제)
   │ 1
   │            1     N
   ├───────< budget
   │ 1          │ 1
   │            │
   └───────< meal_plan >─── N meal >─── N meal_ingredient
                                (budget_id FK)

ingredient_price_ref  (독립 참조 테이블, region별 기준가 시드)
```

## 테이블 정의

### `budget`
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | BIGINT | PK, identity |
| household_id | BIGINT | FK→household(id), NOT NULL, ON DELETE CASCADE |
| amount | NUMERIC(14,2) | NOT NULL, CHECK > 0 |
| currency | VARCHAR(3) | NOT NULL, CHECK in ('KRW','USD') |
| period_start | TIMESTAMPTZ | NOT NULL |
| period_end | TIMESTAMPTZ | NOT NULL, CHECK > period_start |
| locked | BOOLEAN | NOT NULL, default true |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL, default now() |
- 인덱스: `ix_budget_household_period (household_id, period_start)`

### `meal_plan`
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | BIGINT | PK |
| household_id | BIGINT | FK→household, NOT NULL, CASCADE |
| budget_id | BIGINT | FK→budget(id), NOT NULL |
| period_start / period_end | TIMESTAMPTZ | NOT NULL |
| status | VARCHAR(20) | NOT NULL (generating/ready/over_budget/failed) |
| total_cost | NUMERIC(14,2) | NOT NULL, default 0 |
| currency | VARCHAR(3) | NOT NULL |
| region | VARCHAR(2) | NOT NULL (KR/US) |
| created_at | TIMESTAMPTZ | NOT NULL, default now() |
- 인덱스: `ix_mealplan_household_period (household_id, period_start)`

### `meal`
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | BIGINT | PK |
| meal_plan_id | BIGINT | FK→meal_plan(id), NOT NULL, ON DELETE CASCADE |
| plan_date | DATE | NOT NULL |
| meal_type | VARCHAR(16) | NOT NULL (breakfast/lunch/dinner/snack/supper) |
| recipe_name | VARCHAR(200) | NOT NULL |
| recipe_steps | TEXT | NULL |
- 인덱스: `ix_meal_plan_date (meal_plan_id, plan_date)`

### `meal_ingredient`
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | BIGINT | PK |
| meal_id | BIGINT | FK→meal(id), NOT NULL, ON DELETE CASCADE |
| name | VARCHAR(200) | NOT NULL |
| quantity | NUMERIC(10,3) | NOT NULL |
| unit | VARCHAR(16) | NOT NULL |
| est_cost | NUMERIC(14,2) | NULL (기준가 산출값) |
| currency | VARCHAR(3) | NULL |
- 인덱스: `ix_ingredient_meal (meal_id)`

### `ingredient_price_ref` (기준가 시드)
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | BIGINT | PK |
| name | VARCHAR(200) | NOT NULL |
| region | VARCHAR(2) | NOT NULL |
| unit | VARCHAR(16) | NOT NULL |
| pack_qty | NUMERIC(10,3) | NOT NULL, default 1 |
| unit_price | NUMERIC(14,2) | NOT NULL |
| currency | VARCHAR(3) | NOT NULL |
- 유니크: `uq_price_name_region_unit (name, region, unit)`
- 인덱스: `ix_price_region_name (region, name)`

## 마이그레이션 계획 (Alembic)
- **revision 1**: 위 5개 테이블 + 인덱스 + CHECK 생성. `upgrade()` = CREATE, `downgrade()` = DROP(역순).
- **revision 2(데이터)**: `ingredient_price_ref` region별 시드(KR/US) 삽입. downgrade = 시드 DELETE.
- 검증: 로컬 docker-compose DB에서 `upgrade → downgrade → upgrade` 통과 필수.

## 의존성 / 주의
- ⚠️ **`household` 테이블 선행 필요**: budget/meal_plan의 FK 대상. `auth`/`household` 도메인 마이그레이션이 이 기능보다 먼저 존재해야 함 → 미존재 시 household 테이블부터 인프라 요청(순서 조율 필요).
- **누적성 테이블**: `meal_plan`/`meal`/`meal_ingredient`는 사용자·기간별로 누적 → 조회 인덱스(household_id+기간, meal_plan_id) 우선.
- 알레르기·선호는 `household` 도메인 소유(본 기능 테이블 아님) — 조회만.

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 합의)
