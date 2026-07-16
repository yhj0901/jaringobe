# DB 스키마 설계서 — 초기 리비전 (auth + budget v0)

> DDL 은 인프라 에이전트 전담 (`backend/alembic/` 단일 경로). 본 문서가 마이그레이션의 원본 명세다.
> **GATE 3 대상**: 신규 테이블 4개 — 승인 후 `/인프라시작` 으로 초기 리비전 생성.

## 1. ERD

```
users 1 ──── N auth_identities     (소셜 계정 연결 — 현재는 유저당 1개, N 구조로 확장 대비)
users 1 ──── N refresh_tokens      (기기/세션별 세션)
users 1 ──── 1 budget_plans        (v0: 유저당 활성 예산안 1개 — UNIQUE(user_id))
```

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

## 2-7. store_connections (리비전 0005 — GATE 3 대상)

| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | uuid | PK |
| user_id | uuid | NOT NULL FK→users CASCADE |
| store | varchar(10) | CHECK in ('kurly','coupang','ssg','naver') |
| status | varchar(15) | CHECK in ('connected','disconnected') |
| connected_at | timestamptz | NULL |
| created_at/updated_at | timestamptz | NOT NULL |
- **UNIQUE(user_id, store)**, `ix_store_connections_user_id`
- 자격증명 컬럼 없음 — 실연동 시 store 본설계에서 암호화 참조로 확장 (평문 저장 금지 원칙)

## 2-8. notification + 앱 로그인 (리비전 0007 — GATE 3 대상)

> 대상 기획: `docs/기획/앱-웹뷰-푸시알림.md`. 신규 4테이블 + `meal_plans.status` CHECK 확장 — 전부 additive.

**`device_tokens` 신규**
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK gen_random_uuid() | |
| user_id | uuid | NOT NULL FK→users ON DELETE CASCADE | |
| platform | varchar(10) | NOT NULL CHECK in ('ios','android') | |
| token | text | NOT NULL **UNIQUE** | Expo Push Token 원문 (비밀 아님 — 발송 주소. 단 로그엔 마스킹) |
| locale | varchar(10) | NOT NULL default 'ko' | 푸시 템플릿 로캘 |
| timezone | varchar(40) | NOT NULL default 'Asia/Seoul' | IANA |
| app_version | varchar(20) | NULL | |
| last_seen_at | timestamptz | NOT NULL | 앱 실행 시 갱신 |
| created_at / updated_at | timestamptz | NOT NULL | |
- 인덱스: UNIQUE(token) 이 upsert 커버, `ix_device_tokens_user_id`(유저별 발송 대상 조회)
- 삭제: 로그아웃 DELETE, Expo 응답 `DeviceNotRegistered` 즉시 삭제, `last_seen_at` 180일 경과분 배치 삭제

**`notification_settings` 신규**
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL FK→users ON DELETE CASCADE | |
| type | varchar(30) | NOT NULL CHECK in ('meal_reminder_breakfast','meal_reminder_lunch','meal_reminder_dinner','mealplan_done','weekly_nudge') | |
| enabled | boolean | NOT NULL default true | weekly_nudge 만 default false (서비스 레벨) |
| local_time | time | NULL | 리마인더 3종만 사용 (08:00/12:00/18:30 기본) |
| timezone | varchar(40) | NULL | IANA — 로컬시각+존 쌍 저장으로 DST 대응 |
| next_send_at | timestamptz | NULL | **UTC 환산 다음 발송 시각** — 스케줄러 스캔 키 |
| created_at / updated_at | timestamptz | NOT NULL | |
- 제약/인덱스: **UNIQUE(user_id, type)**, **partial index** `ix_notification_settings_due (next_send_at) WHERE enabled AND next_send_at IS NOT NULL` — 스케줄러가 타임존별 전체 스캔 없이 due 행만 인덱스 스캔
- 행 생성: `GET /notifications/settings` 최초 호출 시 lazy 생성 (온보딩 훅 없음)

**`notification_logs` 신규**
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL FK→users ON DELETE CASCADE | |
| device_token_id | uuid | NULL FK→device_tokens **ON DELETE SET NULL** | 토큰 삭제 후에도 이력 보존 |
| type | varchar(30) | NOT NULL | settings.type 과 동일 열거 |
| template_key | varchar(50) | NOT NULL | 본문 원문 저장 금지 — 템플릿 키+변수만 |
| status | varchar(10) | NOT NULL CHECK in ('sent','failed') | |
| error_code | varchar(50) | NULL | Expo 응답 코드 |
| sent_at | timestamptz | NOT NULL | |
- 인덱스: `ix_notification_logs_user_sent (user_id, sent_at)` — weekly_nudge 주 1회 한도 판정 커버
- 보관: **90일** 경과분 배치 삭제 (기획 확정)

**`app_login_codes` 신규**
| 컬럼 | 타입 | 제약 | 설명 |
|------|------|------|------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL FK→users ON DELETE CASCADE | |
| code_hash | char(64) | NOT NULL UNIQUE | SHA-256 hex — **원문 저장 금지** (refresh_tokens 와 동일 원칙) |
| expires_at | timestamptz | NOT NULL | 발급 +60초 |
| used_at | timestamptz | NULL | 단일 사용 마킹 — 재사용 시도는 감사 로그 |
| created_at | timestamptz | NOT NULL | |
- UNIQUE(code_hash) 가 검증 조회 커버. 만료 후 24시간 경과분 배치 삭제

**`meal_plans.status` 확장 (정정 — DDL 변경 없음)**
- ~~CHECK 제약 drop/re-create~~ → **인프라 구현 시 정정 (2026-07-14)**: 실제 스키마에 status CHECK 제약이 없음 (`String(20)`, 서비스 레벨 검증만 — models.py:47). `processing`/`failed` 는 **mealplan 서비스의 열거 검증에만 추가** — 마이그레이션 불필요
- 기존 행은 모두 ready/over_budget — 백필 불필요. `failed` 사유는 기존 `notes` 활용 (API 백엔드 에이전트 통보 사항)

## 3. 마이그레이션 계획 (인프라 에이전트 실행)

| 리비전 | 내용 | 상태 |
|--------|------|------|
| `0001_initial_auth_budget` | 4테이블 + 인덱스/제약 일괄 생성. `CREATE EXTENSION IF NOT EXISTS pgcrypto` (gen_random_uuid) | **적용·검증 완료** (2026-07-09, 로컬 docker postgres 16 에서 upgrade→downgrade→upgrade 왕복 PASS) |
| `0002_mealplan` | mealplan 4테이블 + 인덱스 (팀원 작성, down_revision=0001) | **적용 완료** (2026-07-09 서버·로컬) |
| `0004_household_budget_ext` | household_members 신규 + budget_plans locked/cuisines (down_revision=0003) | **작성·로컬 왕복 검증 PASS** (2026-07-09, GATE 3 통과) |
| `0005_store_connections` | store_connections 신규 (down_revision=0004) | **작성·로컬 왕복 검증 PASS** (2026-07-10, GATE 3 통과) |
| `0006_meal_completion` | meals 에 completed_at·time_minutes·difficulty(NULL) 3컬럼 (down_revision=0005) | **작성·로컬 왕복 검증 PASS** (2026-07-10, GATE 3 통과) |
| `0007_store_connections_global` | store CHECK 에 walmart·instacart 편입 (팀원, `feature/global-region` — **미머지**) | 타 브랜치 리비전 — 0008 의 선행 |
| `0008_notification_app` | device_tokens·notification_settings(partial index `ix_notification_settings_due`)·notification_logs·app_login_codes 4테이블. meal_plans 변경 없음(위 정정). **down_revision=0007 — `feature/global-region` 선머지 필수** | **작성·로컬 왕복 검증 PASS** (2026-07-14, GATE 3 통과) |

- 롤백: 4테이블 역순 drop (최초 리비전이므로 단순, pgcrypto 확장은 유지)
- 파일: `backend/alembic/versions/0001_initial_auth_budget.py`

## 변경 이력
- 2026-07-14: 리비전 0008 작성·로컬 왕복 검증 PASS (GATE 3 통과). meal_plans.status 는 CHECK 부재 확인으로 DDL 불필요 정정, 리비전 번호는 global-region 0007 존재로 0008 로 조정
- 2026-07-14: v1.5 — 2-8 notification 4테이블 + meal_plans.status 확장 설계 (리비전 0007→0008 계획, 설계 토론 5라운드 합의)
- 2026-07-09: v1.2 — 2-6 household_members + budget_plans 확장 설계 (리비전 0004 계획)
- 2026-07-09: 최초 작성 — auth 3테이블 + budget_plans v0 (설계 토론 5라운드 합의)
- 2026-07-09: 리비전 0001 작성·로컬 검증 완료 (GATE 3 통과). rotated_from FK 는 ON DELETE SET NULL 로 확정
- 2026-07-09: 0002(mealplan, 팀원) 문서 회수 — 회원홈-식단연결 설계는 DB 변경 없음(기존 인덱스 커버)
