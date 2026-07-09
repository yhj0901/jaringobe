# CLAUDE.md

이 파일은 Claude Code (claude.ai/code)가 이 저장소의 코드를 다룰 때 참고하는 전역 안내서입니다.

## 세션 진행 상태 관리 (`docs/status/`)

장기 작업(기획, 설계, 구현, QA 등)의 진행 상태를 JSON 으로 `docs/status/` 에 저장하고 `/compact` 시 최신 파일을 우선 참조한다.

**파일 규칙**
- 경로: `docs/status/YYYY-MM-DD_HHMMSS.json`
- 새 작업 시작 또는 중요한 마일스톤 진입 시 새 파일 생성 (덮어쓰기 금지, 시계열 보존)
- 동일 작업의 후속 업데이트는 파일 내 `tasks` / `status` 필드를 갱신하고, 큰 결정/방향 전환은 새 파일로 분리

**JSON 최소 스키마**
```json
{
  "timestamp": "ISO-8601 with timezone",
  "session_topic": "세션의 중심 주제 (기능명 포함)",
  "command": "트리거된 슬래시 커맨드 (예: /API시작 회원 인증)",
  "agent": "사용 중인 에이전트 하네스 경로",
  "status": "현재 상태 한 줄 요약",
  "tasks": [{"id": 1, "subject": "...", "status": "completed|in_progress|pending"}],
  "artifacts": ["산출물 파일 경로 목록"],
  "key_findings": "핵심 발견/결론 (자유 구조)",
  "recommended_actions": "다음 권장 조치 (자유 구조)",
  "pending_user_input": "사용자에게 기다리는 입력 (있을 경우)"
}
```

**`/compact` 운영 규칙 (반드시)**
1. `/compact` 실행 직후, 또는 컨텍스트 압축이 일어났음을 인지한 직후, **`docs/status/` 의 가장 최근 파일을 먼저 읽는다** (`ls -t docs/status/ | head -1`).
2. 그 JSON 의 `session_topic`, `tasks`, `key_findings`, `pending_user_input` 을 기반으로 사용자에게 현재 상태를 1~2 문단으로 요약 보고한다.
3. 압축으로 잃었을 수 있는 직전 결정/가설 데이터는 status JSON 으로 복원한다 — 추측하지 말 것.
4. status 파일과 현재 워킹 트리가 불일치하면 워킹 트리를 신뢰하고 status JSON 을 갱신.
5. 새로운 마일스톤이 발생하거나 사용자 응답으로 방향이 바뀌면 새 status 파일을 만들어 누적.

**금지**
- status JSON 에 비밀(키/토큰/PII)·평문 자격증명 기록
- 동일 시각 파일 덮어쓰기 (시계열 손실)
- status JSON 만 보고 응답 — 항상 워킹 트리·git log 와 교차 확인

## 문서 옵시디언 미러링 (필수)

`docs/` 에 남기는 문서는 옵시디언 볼트에도 동일하게 남긴다.

- **볼트 경로**: `/Users/yangheejun/Documents/Obsidian Vault/자린고비/docs/` (저장소 `docs/` 와 동일한 하위 구조 유지)
- **대상**: `docs/**/*.md` 마크다운 문서 전체 (`docs/status/*.json` 은 세션 관리용이므로 제외)
- **시점**: `docs/` 에 .md 파일을 생성·수정한 직후 매번 복사한다 (턴 종료 전 일괄 1회도 허용)
- **방법**: 경로에 공백이 있으므로 반드시 따옴표 처리
  ```bash
  rsync -a --include='*/' --include='*.md' --exclude='*' docs/ "/Users/yangheejun/Documents/Obsidian Vault/자린고비/docs/"
  ```
- 저장소에서 문서를 이동/삭제한 경우 미러 쪽도 동일하게 반영한다 (단, 볼트 쪽에서 사용자가 직접 수정한 파일을 발견하면 덮어쓰기 전에 사용자에게 확인)
- 진실의 원본(source of truth)은 항상 저장소 `docs/` — 볼트는 읽기용 미러

## 프로젝트 개요

**JARINGOBE(자린고비)** 는 **예산 안에서 식단을 자동 생성하고, 가상 냉장고로 버려지는 식재료를 0으로 만들고, 식재료를 자동 주문하는 알뜰 식생활 플랫폼**입니다. (*GO BE SMART, SAVE BIG.*)
Next.js 프론트엔드와 FastAPI 백엔드, PostgreSQL 데이터베이스로 구성되며 단일 저장소(모노레포)로 관리합니다.

**제품 방향의 기준 문서**: `docs/사업/사업계획서-요약.md` — 기획/설계 에이전트는 작업 전 반드시 읽는다.

### 핵심 기능 (3대 축)
1. **예산 락 내 AI 식단 자동 생성** — 가구 구성·식단 방향·선호에 맞춰 연동 마트 재료 기반 식단 + 조리법
2. **가상 냉장고 (Zero-UX)** — 배송 시 자동 등록, 식사 완료 체크 시 자동 차감, 유통기한 임박 재료 우선 배치
3. **식재료 자동 주문** — 주 1~2회 예산 내 자동 결제·배송, 냉장고 잔여분만큼 다음 주문 자동 감산

### 서비스 도메인
`auth`(소셜 로그인) · `household`(가구 구성) · `budget`(예산 락) · `mealplan`(AI 식단) · `fridge`(가상 냉장고) · `order`(자동 주문) · `store`(마트 연동) · `subscription`(프리미엄 구독)
— 백엔드 라우터/서비스/모델과 프론트 features/ 디렉토리는 이 도메인 분류를 따른다.

### 글로벌 전략 (설계 필수 고려사항)
- **국내**: 공식 자동 결제 API 부재 → 사용자 보유 마트 계정 연동으로 장바구니·주문 자동화 (마켓컬리/쿠팡/SSG/네이버)
- **글로벌(미국)**: 주 1회 대량 배송 + 식재료 수명 극대화 알고리즘, Walmart·Instacart Connect API 연동 추진
- 따라서 처음부터: **다국어(ko/en) · 다중 통화(KRW/USD) · 타임존 · 국가별 마트 어댑터** 를 전제로 설계한다

## 프로젝트 구조

| 디렉토리 | 역할 | 기술 스택 | 담당 에이전트 |
|----------|------|-----------|--------------|
| **frontend/** | 웹 프론트엔드 | Next.js (App Router), TypeScript | UI 프론트엔드 |
| **backend/** | REST API 백엔드 | Python, FastAPI, SQLAlchemy 2.0(async), Pydantic v2 | API 백엔드 |
| **backend/alembic/** | DB 마이그레이션 | Alembic | 인프라 (전담) |
| **docker/** · `docker-compose.yml` | 로컬 개발/배포 환경 | Docker, PostgreSQL | 인프라 |
| **docs/** | 기획/설계/테스트/상태 문서 | Markdown | 전체 |

## 확정 기술 스택

```
UI 프론트엔드: Next.js 14+ (App Router) / TypeScript strict / Tailwind CSS
다국어      : next-intl (ko/en) — 라우팅 로캘 프리픽스 포함
API 백엔드  : Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async) / Pydantic v2
패키지 관리 : 백엔드 uv / 프론트엔드 npm
DB          : PostgreSQL 16 / Alembic 마이그레이션
인증        : 소셜 로그인 (카카오/구글/애플) + JWT (Access + Refresh) — 상세는 docs/설계/security-design.md
AI 식단     : LLM 기반 식단 생성 — 모델/프롬프트 구조는 설계 단계에서 확정
마트 연동   : store 도메인 어댑터 패턴 (KR 계정 연동 / US Walmart·Instacart API)
로컬 환경   : docker-compose (postgres 포함)
테스트      : 백엔드 pytest + httpx / 프론트엔드 vitest + testing-library
```

## 프로젝트 간 공통 사항

| 항목 | 내용 |
|------|------|
| DB | PostgreSQL · 마이그레이션은 Alembic(`backend/alembic/`) 단일 경로 · DDL 은 인프라 에이전트 전담 |
| API 계약 | `docs/설계/api-spec.md` 가 프론트↔백엔드 계약서. 임의 변경 금지 |
| 다국어(i18n) | UI 기본 한국어 + 영어 지원. 모든 UI 텍스트는 i18n 키로 관리 — `ko.json`, `en.json` **동시 수정** 필수. 하드코딩 문자열 금지 |
| 통화/시간 | 금액은 `Decimal(numeric)` + 통화 코드(KRW/USD) 쌍으로 저장 (float 금지). 시각은 **UTC 저장**, 로캘별 표시(통화·날짜 포맷)는 프론트 담당 |
| 마트 연동 | 국가별 어댑터 패턴 (`store` 도메인) — KR: 계정 연동 자동화 / US: Walmart·Instacart 공식 API. 공통 인터페이스 뒤로 격리 |
| 개인정보 | 수집 최소화. 국내 개인정보보호법 + 글로벌(GDPR/CCPA) 요구를 기획·설계 단계에서 검토 |
| 인코딩 | UTF-8 |
| 시크릿 | `.env` 로만 관리 (`.env.example` 커밋, `.env` 커밋 금지). 코드 하드코딩 금지. 마트 연동 자격증명은 반드시 암호화 저장 |
| 언어 | 코드 주석·문서·커밋 메시지의 기본 언어는 **한국어** |

---

## AI 에이전트 오케스트레이션 파이프라인

Claude Code가 오케스트레이터 역할을 수행하며, GATE 승인 기반으로 전체 개발 흐름을 관리한다.

### 파이프라인

```
/기획시작 → GATE 1 승인
  → /설계시작 → GATE 2 승인
    → /API시작 + /UI시작 (병렬)
      → GATE 3 (DB 스키마 변경 검증 — /인프라시작)
        → /QA시작 → /문서시작
```

- GATE 승인은 사용자가 "기획 승인", "설계 승인" 등으로 입력
- 각 커맨드는 `agents/` 폴더의 해당 에이전트 하네스를 먼저 로드한 뒤 실행. "반드시/금지" 규칙 엄수.

### 에이전트 구성

| 에이전트 | 파일 | 역할 | 기술 스택 |
|----------|------|------|-----------|
| 기획 | `agents/planning.md` | 요구사항 토론 → 기획문서 | - |
| 설계 | `agents/design.md` | 아키텍처/API/DB 설계 | 전체 |
| API 백엔드 | `agents/backend.md` | FastAPI REST API 구현 | Python/FastAPI/PostgreSQL |
| UI 프론트엔드 | `agents/frontend.md` | Next.js 웹 UI 구현 | Next.js/TypeScript |
| 인프라 | `agents/infra.md` | DB 마이그레이션/배포/설정 관리 | PostgreSQL/Alembic/Docker |
| QA | `agents/qa.md` | 통합/보안/시나리오 테스트 | - |
| 문서 | `agents/docs.md` | 기술문서/릴리즈노트 | - |

### 에이전트 간 격리 및 DB 동기화

**코드 격리** — 각 에이전트는 자기 담당 영역만 수정. 다른 영역 변경 필요 시 해당 에이전트에 요청하거나 오케스트레이터 에스컬레이션.

| 에이전트 | 수정 가능 영역 |
|----------|---------------|
| API 백엔드 | `backend/` (단, `backend/alembic/` 은 인프라와 협의) |
| UI 프론트엔드 | `frontend/` |
| 인프라 | `backend/alembic/`, `docker/`, `docker-compose.yml`, CI 설정, `.env.example` |
| 문서 | `docs/` |

**DB 공유 자원 원칙**
- DDL 변경(테이블/컬럼/인덱스 생성·수정·삭제)은 **인프라 에이전트만** 수행. 다른 에이전트는 요청만.
- 마이그레이션은 **`backend/alembic/` 단일 경로** 로 통합 관리 (SQL 직접 실행 금지)
- 변경 후 `docs/설계/db-schema.md` 갱신
- UI 는 DB 직접 접근 안 함 (반드시 API 경유)

### 에이전트 공통 — 작업 시작 전 선행 작업 (필수)

모든 에이전트(`agents/*.md`)는 실제 작업(분석·수정·문서 작성 등) 전에 반드시 다음을 수행한다.

```bash
# 1. 워킹 트리 상태 확인
git status

# 2. 원격 최신 변경 확인
git fetch

# 3. 로컬 변경이 없고 behind 상태이면 fast-forward pull
git pull --ff-only
```

**판정 규칙**
| 상황 | 조치 |
|------|------|
| `git status` 가 clean + behind 있음 | `git pull --ff-only` 실행 |
| uncommitted 변경 있음 + behind 있음 | 사용자에게 알림 후 대기 (자동 stash 금지) |
| 충돌 발생 또는 non-fast-forward | 사용자에게 즉시 보고, 작업 중단 |
| 원격과 동기화 완료 (up to date) | 바로 작업 진행 |

**금지**
- `git pull` (rebase/merge 자동 선택 금지, 반드시 `--ff-only`)
- `git reset --hard`, `git push --force`, 충돌 자동 해결
- 사용자의 uncommitted 변경을 자동 stash/discard
- 다른 브랜치로 자동 전환 (`git checkout`)

서브 에이전트로 분할 실행하는 경우에도 **세션 시작 시 1회만** 수행하면 된다 (에이전트 내부 단계마다 반복 금지).

### GATE 승인 기준

| GATE | 조건 | 승인 방법 |
|------|------|-----------|
| GATE 1 (기획→설계) | 기획문서 완성, 미결사항 0건 | "기획 승인" |
| GATE 2 (설계→구현) | 설계 산출물 완성, API 스펙 합의 | "설계 승인" |
| GATE 3 (DB 스키마) | DB 변경 시 마이그레이션 검증 | "DB 승인" / 변경 없으면 자동 |
| GATE 4 (QA→문서) | Critical/High 버그 0건 | QA 에이전트 자동 |

### 코드 수정 및 테스트 규칙

**수정-테스트 루프**
```
수정 명세서 승인 → 코드 수정 → 단위 테스트 → PASS(커버리지 90%+) → 커밋
                                          ↳ FAIL → 분석·수정 반복(최대 10회) → 초과 시 설계 재검토 에스컬레이션
```

**필수 규칙**
1. 수정 시 해당 기능 단위 테스트 작성/실행 필수
2. 커버리지 90% 미만 커밋 금지
3. 테스트 실패 시 10회 한도 재시도, 초과 시 에스컬레이션
4. 수정 명세서에 명시되지 않은 파일/함수 수정 금지
5. 기존 코드의 리팩토링·변수명 변경·import 정리 등 무관한 변경 금지

### 협업 규칙 (다인 개발 — 반드시)

2인 이상이 backend/DB 를 동시 수정하는 상황을 전제로 한다.

1. **작업 시작·커밋 직전 `git fetch` + `git pull --ff-only`** — 세션 중에도 커밋 전엔 반드시 재동기화. behind 상태로 push 금지
2. **브랜치 분리**: 서로 다른 기능은 반드시 별도 feature 브랜치. main 직접 커밋 금지. 머지는 PR 로만
3. **Alembic 리비전 선형성**: 새 리비전 작성 전 `git fetch` 후 **모든 원격 브랜치의 `backend/alembic/versions/`** 를 확인해 down_revision 이 최신 head 를 가리키게 한다. 두 브랜치가 같은 down_revision 을 가리키면 나중에 머지하는 쪽이 리베이스 (조정은 인프라 에이전트 전담)
4. **DB 스키마 중복 금지**: 같은 개념의 테이블을 브랜치별로 따로 만들지 않는다 (예: budget vs budget_plans). 신규 테이블 전 `docs/설계/db-schema.md` 와 원격 브랜치의 versions/ 를 먼저 확인하고, 겹치면 설계 에이전트 재소집
5. **공유 개발 DB = 배포 서버의 `docker-db-1`** (docker/docker-compose.server.yml 기동분). 접속은 SSH 터널로만: `ssh -i {pem} -L 15432:localhost:5432 ubuntu@121.78.130.230` 후 `localhost:15432` — DB 포트를 공인망에 열지 않는다
6. 공유 DB 에 실험적 마이그레이션을 적용할 때는 운영 DB(`jaringobe`)가 아닌 **개발용 DB(`jaringobe_dev`)** 를 사용하고, 운영 DB 마이그레이션은 main 머지 후에만 적용

### Git Convention

```
기반 브랜치: main
브랜치     : feature/{기능} / fix/{버그} / improve/{기능} / chore/{작업}
커밋       : feat/fix/refactor/style/test/docs/chore/db: {내용}   ← Conventional Commits, 한국어 메시지
흐름       : 브랜치 분기 → 구현 + 테스트(커버리지 90%+) PASS → 커밋 → 리뷰 → 승인 → main 머지
```

- 커밋·푸시는 사용자 승인 후에만 수행 (`/커밋` 커맨드 사용)
- DB 마이그레이션 포함 커밋은 커밋 메시지 prefix 를 `db:` 로 사용

### 보조 커맨드

| 커맨드 | 용도 |
|--------|------|
| `/인프라시작` | DB 스키마 변경, 마이그레이션, Docker/배포 설정 |
| `/커밋` | 변경 파일 확인 → 사용자 승인 → 커밋 + 푸시 |
