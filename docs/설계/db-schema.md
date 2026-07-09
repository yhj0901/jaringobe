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

## 3. 마이그레이션 계획 (인프라 에이전트 실행)

| 리비전 | 내용 | 상태 |
|--------|------|------|
| `0001_initial_auth_budget` | 4테이블 + 인덱스/제약 일괄 생성. `CREATE EXTENSION IF NOT EXISTS pgcrypto` (gen_random_uuid) | **적용·검증 완료** (2026-07-09, 로컬 docker postgres 16 에서 upgrade→downgrade→upgrade 왕복 PASS) |

- 롤백: 4테이블 역순 drop (최초 리비전이므로 단순, pgcrypto 확장은 유지)
- 파일: `backend/alembic/versions/0001_initial_auth_budget.py`

## 변경 이력
- 2026-07-09: 최초 작성 — auth 3테이블 + budget_plans v0 (설계 토론 5라운드 합의)
- 2026-07-09: 리비전 0001 작성·로컬 검증 완료 (GATE 3 통과). rotated_from FK 는 ON DELETE SET NULL 로 확정
