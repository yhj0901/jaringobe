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

### 3-4. 회원 홈 (v1.1 — 회원홈-식단연결)
```
로그인 홈 진입 → GET /users/me
  hasBudgetPlan=false → BudgetDraftFlow(재사용) → POST /budget/plans(onboarding)
  → GET /mealplans/latest
      404 → 빈 상태 히어로 → 생성 시트 → POST /mealplans (LLM, 폴백 내장) → 표시
      200 → MealPlanResponse → ViewModel 매핑 → HomeShell(mode=member)
냉장고/자동주문 카드는 "준비 중" 잠금 (fridge/order 도메인 구현 시 해제)
```

## 3-5. 앱 로그인 — 원타임 코드 세션 인계 (v1.5)

> 문제: 구글은 웹뷰 내 OAuth 를 차단(`disallowed_useragent`). 커스텀 탭/시스템 브라우저에서 OAuth 를 진행하면 쿠키가 **외부 브라우저**에 세팅되어 웹뷰 세션이 생기지 않는다. → 원타임 코드로 세션을 웹뷰에 인계한다. 앱에서는 3사 provider 모두 이 경로로 통일.

```
[웹(웹뷰 내)] 로그인 버튼 → 브리지 LOGIN_PROVIDER(provider, next)
[앱] 커스텀 탭(iOS SFSafariViewController / Android Custom Tabs) 오픈:
     /api/v1/auth/{provider}/authorize?client=app&next={next}
[백엔드] state(client=app 포함) → provider → callback
     → users upsert (기존 3-2 와 동일)
     → 쿠키 대신 원타임 코드 발급 (60초·단일사용·해시 저장)
     → 302 jaringobe://auth?code={code}&next={next}
[앱] 딥링크 수신 → 커스텀 탭 닫기 → 웹뷰 내비게이트:
     /api/v1/auth/app/session?code={code}&next={next}
[백엔드] 코드 검증·소진 → Set-Cookie (웹뷰 쿠키 저장소에 세팅) → 302 {next}?login=success
[웹] 이후 기존 3-2 후속 흐름과 동일 (GET /users/me 분기)
```
- 웹 브라우저 로그인(3-2)은 변경 없음 — `client` 파라미터 부재 시 기존 동작
- 커스텀 스킴(`jaringobe://`)은 P0, Universal Links/App Links 전환은 P1 (security-design 5-4)

## 3-6. 식단 생성 비동기 + 완료 푸시 (v1.5)

```
[웹/앱] POST /mealplans → 202 {id, status:"processing"} → GenerationLoading + GET /mealplans/{id} 폴링(3s, 백오프, 최대 3분)
[백엔드] BackgroundTasks 로 LLM 생성 실행 (MVP: FastAPI 인프로세스 — 단일 인스턴스 전제)
     완료 → status=ready|over_budget 저장 → notification.service 호출
     실패(폴백 포함 전부) → status=failed + notes
[notification.service] mealplan_done enabled 확인 → 유저의 device_tokens 전체에 Expo Push 발송
     → 응답 DeviceNotRegistered → 해당 토큰 삭제 / 발송 결과 notification_logs 기록
[앱] 푸시 탭 → data.path 화이트리스트 검증 → 웹뷰 내비게이트 (/mealplan/{id})
```
- **푸시는 보조 채널** — 화면 폴링이 기본. 앱 미설치 웹 사용자도 동일 폴링으로 완주
- 멀티 인스턴스 배포 시 확장점: BackgroundTasks → 외부 워커(큐), 5절 후속 확장점에 기록

## 3-7. 식사 리마인더 스케줄러 (v1.5)

```
[스케줄러] FastAPI lifespan 에서 asyncio 태스크 기동 — 30초 주기:
  SELECT ... FROM notification_settings
   WHERE enabled AND next_send_at <= now()          ← partial index 스캔
  각 행에 대해 발송 직전 재확인:
    ① 오늘(설정 timezone 기준 로컬 날짜)의 해당 끼니 meal 존재?
    ② completed_at IS NULL?
    ③ 최신 enabled 상태? (race 방지)
  전부 예 → 푸시 발송 ("오늘 점심: {recipeName} — 지금 만들어 볼까요?")
  아니오 → 발송 스킵 (로그 없음)
  공통 → next_send_at = 다음 날 동일 로컬시각의 UTC 환산값으로 갱신
```
- 단일 인스턴스 전제 (현 배포 구조). 멀티 인스턴스 시 어드바이저리 락 또는 스케줄러 프로세스 분리 — 후속 확장점
- weekly_nudge(P2): 동일 스케줄러에 편입, notification_logs 로 주 1회 한도 판정

## 3-8. 모바일 앱 쉘 구성 (v1.5 — 상세: mobile-app.md)

```
mobile/  (Expo — UI 프론트엔드 에이전트 관할 확장)
  app.json / eas.json          # 앱 메타·스킴(jaringobe)·EAS 빌드 프로필
  App.tsx                      # 스플래시 → WebView(배포 오리진) 단일 화면
  src/
    webview.tsx                # 오리진 allowlist·외부 링크 시스템 브라우저 위임·뒤로가기
    bridge.ts                  # postMessage JSON 프로토콜 (v:1)
    push.ts                    # expo-notifications 권한·토큰·수신 핸들러
    deeplink.ts                # jaringobe:// 수신 (auth 코드 / 푸시 path 라우팅)
```
- 웹뷰 UA 에 `JaringobeApp/{version} ({platform})` 접미사 — 웹이 앱 내 실행 감지
- frontend 는 `shared/bridge/` 모듈 신설 (ui-design.md 12장)

## 4. 환경 변수 (.env — 인프라 에이전트가 .env.example 관리)

| 키 | 위치 | 용도 |
|----|------|------|
| `DATABASE_URL` | backend | postgresql+asyncpg 접속 |
| `JWT_SECRET` / `JWT_ALG=HS256` | backend | JWT·state 서명 |
| `KAKAO_CLIENT_ID/SECRET`, `GOOGLE_CLIENT_ID/SECRET`, (P1) `APPLE_*` | backend | OAuth |
| `FRONTEND_ORIGIN` | backend | Origin 검증·리다이렉트 베이스 |
| `BACKEND_URL` | frontend | rewrites 대상 |
| `EXPO_ACCESS_TOKEN` | backend | Expo Push API 인증 (v1.5) |
| `APP_SCHEME=jaringobe` | backend | 앱 로그인 코드 리다이렉트 스킴 (v1.5) |
| `WEB_URL` | mobile (EAS) | 웹뷰가 로드할 배포 웹 오리진 (v1.5) |

## 5. 선행/후속 의존성
- **선행**: docker-compose(postgres) + Alembic 초기 리비전 — `/인프라시작` (GATE 3)
- **후속 확장점**: 홈 셸의 데이터 주입 인터페이스(게스트 샘플 ↔ 회원 실데이터), budget_plans 확장(budget 본설계), 애플 어댑터(P1), store 어댑터(마트 연동 기획 시), rate limit 인메모리 → Redis 교체(멀티 인스턴스 배포 시), **BackgroundTasks → 워커/큐 분리 + 스케줄러 프로세스 분리(멀티 인스턴스 시)**, **Universal Links/App Links(P1)**, **Apple 4.2 리젝 시 네이티브 탭바 Plan B**

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 5라운드 합의)
- 2026-07-09: v1.1 — 회원 홈 흐름(3-4) 추가
- 2026-07-14: v1.5 — 앱 웹뷰 + 푸시: 3-5 앱 로그인(원타임 코드), 3-6 생성 비동기+푸시, 3-7 리마인더 스케줄러, 3-8 mobile/ 구조, 환경 변수 3종 추가
