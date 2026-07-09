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

## 4. 환경 변수 (.env — 인프라 에이전트가 .env.example 관리)

| 키 | 위치 | 용도 |
|----|------|------|
| `DATABASE_URL` | backend | postgresql+asyncpg 접속 |
| `JWT_SECRET` / `JWT_ALG=HS256` | backend | JWT·state 서명 |
| `KAKAO_CLIENT_ID/SECRET`, `GOOGLE_CLIENT_ID/SECRET`, (P1) `APPLE_*` | backend | OAuth |
| `FRONTEND_ORIGIN` | backend | Origin 검증·리다이렉트 베이스 |
| `BACKEND_URL` | frontend | rewrites 대상 |

## 5. 선행/후속 의존성
- **선행**: docker-compose(postgres) + Alembic 초기 리비전 — `/인프라시작` (GATE 3)
- **후속 확장점**: 홈 셸의 데이터 주입 인터페이스(게스트 샘플 ↔ 회원 실데이터), budget_plans 확장(budget 본설계), 애플 어댑터(P1), store 어댑터(마트 연동 기획 시), rate limit 인메모리 → Redis 교체(멀티 인스턴스 배포 시)

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 5라운드 합의)
