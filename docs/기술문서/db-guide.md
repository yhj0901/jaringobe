# DB 스키마 가이드

> 원본: `docs/설계/db-schema.md`. DDL 은 **인프라 에이전트 전담**, `backend/alembic/` 단일 경로.

## 현재 스키마 (리비전 `0001_initial_auth_budget`)

```
users 1─N auth_identities   (UNIQUE(provider, provider_user_id) 가 로그인 조회 커버)
users 1─N refresh_tokens    (token_hash 는 SHA-256 — 원문 저장 금지)
users 1─1 budget_plans      (v0: UNIQUE(user_id), budget 본설계에서 확장 예정)
```

## 전역 규칙 (모든 신규 테이블 적용)
- PK `uuid` + `gen_random_uuid()` (pgcrypto)
- 시각은 `timestamptz` **UTC** — `timestamp without time zone` 금지
- 금액은 `numeric` + `char(3)` 통화 코드 쌍 — float/real 금지
- 열거값은 CHECK 제약 (`ck_{테이블}_{컬럼}` 네이밍), 인덱스는 `ix_`, 유니크는 `uq_`
- users 삭제 시 하위 테이블 CASCADE (탈퇴 기획 시 soft delete 재검토 예정)

## 마이그레이션 절차
```bash
cd backend
uv run alembic upgrade head        # 적용
uv run alembic downgrade -1        # 롤백 (모든 리비전은 downgrade 필수)
uv run alembic history
```
- 새 리비전은 반드시 인프라 에이전트가 GATE 3 승인 후 작성 → 로컬 docker DB 에서 upgrade→downgrade→upgrade 왕복 검증 → `docs/설계/db-schema.md` 갱신
- SQLAlchemy 모델(`domains/*/models.py`)은 마이그레이션과 1:1 유지 (백엔드 테스트가 `compare_metadata` diff 0건으로 검증)

## 데이터 보관
- `refresh_tokens`: 만료/폐기 후 30일 경과분 배치 삭제 대상 (배치 작업은 미구현 — 후속)
- 이메일은 null 허용 (카카오 동의 거부) — 전 도메인이 null 전제로 다뤄야 함

---

## v0.2.0 증분 — 리비전 0008_notification_app (2026-07-16)

> 상세: `docs/설계/db-schema.md` 2-8

- 신규 4테이블: `device_tokens`(token UNIQUE) · `notification_settings`(UNIQUE(user_id,type), partial index `ix_notification_settings_due`) · `notification_logs`(90일 보관, template_key 만) · `app_login_codes`(해시·60초)
- `meal_plans.status` 는 DDL 변경 없음 (CHECK 부재 — 서비스 검증으로 processing/failed 확장)
- **적용 순서 주의**: down_revision=0007(`feature/global-region`) — 해당 브랜치 머지 후 `alembic upgrade head`
