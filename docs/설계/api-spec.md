# API 스펙 — v1 (프론트↔백엔드 계약서)

> 이 문서는 프론트↔백엔드 계약서다. 변경은 반드시 "API 스펙 변경 프로세스"(agents/design.md)를 따른다.
> 대상 기능: 소셜 로그인(auth) + 게스트 예산안 이전(budget). UI 대변인 동의 완료 (2026-07-09).

## 0. 공통 규격 (전 API 적용 — 최초 확정)

| 항목 | 규격 |
|------|------|
| Base URL | `/api/v1` (프론트는 Next.js rewrites 로 동일 오리진 호출) |
| 케이스 | 요청/응답 JSON 모두 **camelCase** (Pydantic v2 `alias_generator=to_camel`, `populate_by_name=True`) |
| 금액 | `{"amount": "500000.00", "currency": "KRW"}` — amount 는 **문자열**(Decimal 직렬화), currency 는 ISO 4217. float 금지 |
| 시각 | ISO-8601 UTC (`2026-07-09T04:00:00Z`) |
| 인증 | httpOnly 쿠키 (`jaringobe_access`, `jaringobe_refresh`) — 상세는 `security-design.md`. Authorization 헤더 미사용 |
| 페이지네이션 | `?page=1&size=20&sort=-createdAt` (본 범위엔 목록 API 없음 — 규격만 선확정) |
| 에러 응답 | 아래 공통 구조 |

### 에러 공통 구조
```json
{ "detail": { "code": "AUTH_INVALID_STATE", "message": "OAuth state validation failed" } }
```
- `code`: 기계 판독용 — **프론트가 i18n 키로 매핑**해 사용자 문구 표시 (API 는 노출 문구를 직접 내리지 않는다)
- `message`: 개발자용 영문 설명 (UI 표시 금지)
- 검증 오류(422)는 FastAPI 기본 배열에 `code: "VALIDATION_ERROR"` 를 래핑

### 공통 에러 코드
| HTTP | code | 의미 |
|------|------|------|
| 401 | `AUTH_REQUIRED` | 인증 쿠키 없음/만료 |
| 401 | `AUTH_TOKEN_REVOKED` | 재사용 감지 등으로 폐기된 토큰 |
| 403 | `FORBIDDEN_ORIGIN` | Origin 검증 실패 |
| 422 | `VALIDATION_ERROR` | 입력 검증 실패 |
| 429 | `RATE_LIMITED` | 요청 한도 초과 |

---

## 1. auth 도메인

### 1-1. `GET /api/v1/auth/{provider}/authorize` — 인증 불필요
소셜 로그인 시작. provider 인가 페이지로 302 리다이렉트. (JSON API 아님 — 브라우저 내비게이션 전용)

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `provider` (path) | `kakao \| google \| apple` | apple 은 P1 (미구현 시 404 `PROVIDER_NOT_SUPPORTED`) |
| `next` (query, optional) | string | 로그인 완료 후 복귀할 **상대 경로**. 화이트리스트 검증(CWE-601), 기본 `/` |
| `client` (query, optional) | `web \| app` | **v1.5 신규.** 기본 `web`. `app` 이면 콜백에서 쿠키 대신 원타임 코드 발급(1-6) — 앱은 전 provider 를 커스텀 탭/시스템 브라우저에서 진행 |

- 동작: 서명된 `state`(nonce + next + client + 10분 만료) 생성 → provider 인가 URL 로 302

### 1-2. `GET /api/v1/auth/{provider}/callback` — 인증 불필요
provider 콜백. 성공 시 쿠키 세팅 후 프론트로 302. (JSON API 아님)

- 성공: `Set-Cookie` (access/refresh) → `302 {next}?login=success`
- 실패: `302 /login?error={code}` — code:

| error code | 상황 |
|------------|------|
| `AUTH_PROVIDER_DENIED` | 사용자가 동의 거부 |
| `AUTH_INVALID_STATE` | state 검증 실패/만료 |
| `AUTH_PROVIDER_ERROR` | provider 응답 오류/타임아웃 |
| `AUTH_EMAIL_CONFLICT_NOTICE` | 동일 이메일 타 provider 계정 존재 — **로그인은 정상 진행**되며 프론트가 안내 배너만 표시 (FR-004). 이 경우 `302 {next}?login=success&notice=AUTH_EMAIL_CONFLICT_NOTICE` |

- 신규/기존 판정은 콜백에서 내리지 않는다 — 프론트는 복귀 후 `GET /users/me` 로 분기
- **`client=app` 분기 (v1.5)**: 쿠키를 세팅하지 않고 **원타임 앱 로그인 코드**(256bit 랜덤, 60초 만료, 단일 사용, DB 에 SHA-256 해시만 저장) 발급 → `302 jaringobe://auth?code={원문}&next={next}` / 실패 시 `302 jaringobe://auth?error={code}` — 커스텀 탭에서 진행된 OAuth 의 세션을 웹뷰로 인계하기 위함 (상세 흐름: architecture.md 3-5)

### 1-6. `GET /api/v1/auth/app/session` — 인증 불필요 (v1.5 신규)
원타임 앱 로그인 코드 → 웹뷰 쿠키 교환. **앱이 웹뷰를 이 URL 로 내비게이트**해야 쿠키가 웹뷰 쿠키 저장소에 세팅된다. (JSON API 아님)

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `code` (query) | string | 원타임 코드 원문 |
| `next` (query, optional) | string | 상대 경로 화이트리스트 검증 (CWE-601), 기본 `/` |

- 성공: 코드 해시 대조·만료·단일사용 검증 → `used_at` 마킹 → `Set-Cookie`(access/refresh) → `302 {next}?login=success`
- 실패: `302 /login?error=AUTH_INVALID_APP_CODE` (만료/재사용/위조 동일 코드 — 재사용 시도는 감사 로그)
- rate limit: IP 10회/분

### 1-3. `POST /api/v1/auth/refresh` — refresh 쿠키 필요
Access 재발급 + refresh 회전.

- 요청 본문: 없음 (쿠키 기반)
- `200` 응답: `{}` + 신규 쿠키 세트
- `401 AUTH_TOKEN_REVOKED`: 재사용 감지 → 해당 유저 전 세션 폐기됨. 프론트는 로그인 페이지로

### 1-4. `POST /api/v1/auth/logout` — 인증 필요
- `204`: refresh 서버측 폐기 + 쿠키 삭제. (access 만료 전 탈취 대비 만료시각까지 무시 목록 처리 여부는 구현 노트 참조)

### 1-5. `GET /api/v1/users/me` — 인증 필요
로그인 직후 분기 판정용 단일 콜. (auth 도메인 라우터에서 제공)

```json
// 200 UserMeResponse
{
  "id": "8a6f...uuid",
  "nickname": "자린이",
  "email": "user@example.com",        // null 가능 (카카오 동의 거부)
  "profileImageUrl": null,
  "locale": "ko",
  "country": "KR",
  "currency": "KRW",
  "onboardingCompleted": false,
  "hasBudgetPlan": false
}
```

---

## 2. budget 도메인

### 2-1. `POST /api/v1/budget/plans` — 인증 필요
예산안 생성. **게스트 예산안 이전(FR-108)** 과 추후 온보딩 생성이 공용으로 사용.

```json
// 요청 BudgetPlanCreateRequest
{
  "householdSize": 4,
  "budget": { "amount": "700000", "currency": "KRW" },
  "mealDirection": "kids",            // health | diet | hearty | kids
  "source": "guest"                   // guest | onboarding
}
```

- 서버측 전량 재검증 (CWE-20/602 — 클라이언트 값 불신):
  - `householdSize`: 1~10 정수
  - `budget.currency`: `KRW | USD`, `amount`: KRW 50,000~5,000,000 / USD 50~5,000 (Decimal, 소수 2자리 이내)
  - `mealDirection`: 열거값
- 응답:

| HTTP | 내용 |
|------|------|
| `201` | `BudgetPlanResponse` (아래) |
| `409 BUDGET_PLAN_EXISTS` | 이미 활성 예산안 보유 — 프론트는 로컬 게스트 데이터 삭제만 수행 |
| `422 VALIDATION_ERROR` | 범위/열거 위반 — 프론트는 게스트 값 폐기(변조 의심) 후 일반 온보딩 |

```json
// 201 BudgetPlanResponse
{
  "id": "3c9d...uuid",
  "householdSize": 4,
  "budget": { "amount": "700000.00", "currency": "KRW" },
  "mealDirection": "kids",
  "source": "guest",
  "createdAt": "2026-07-09T04:00:00Z"
}
```

### 2-2. `GET /api/v1/budget/plans` — 인증 필요 (v1.3.1 신규)
내 예산안 현재값 (설정 페이지 요약·부분 수정 병합용). `200` BudgetPlanResponse(locked·cuisines 포함) / `404 BUDGET_PLAN_NOT_FOUND`.

---

## 3. mealplan 도메인 (v1.1 — 구현 기준 정식 편입)

> 팀원 구현(PR #8)을 계약으로 정식화. 요청/응답은 camelCase, id 는 uuid, 금액은 Money(문자열+통화).

### 3-1. `GET /api/v1/mealplans/latest` — 인증 필요 **(v1.1 신규 — 백엔드 구현 필요)**
인증 유저의 가장 최근 식단 1건 (`created_at DESC LIMIT 1`, 기존 인덱스 `ix_meal_plans_user_created` 커버).

| HTTP | 내용 |
|------|------|
| `200` | `MealPlanResponse` (3-2 와 동일 구조) |
| `404 MEALPLAN_NOT_FOUND` | 생성 이력 없음 — 프론트 빈 상태 분기 전용 코드 |

### 3-2. `POST /api/v1/mealplans` — 인증 필요 **(v1.5 변경 — 비동기 전환)**
```json
// 요청 MealPlanCreateRequest
{ "days": 7, "mealsPerDay": 3, "allergies": ["땅콩"], "preferences": ["한식"] }
```
- `days` 1~31, `mealsPerDay` 1~5. `allergies`/`preferences` 는 항목당 30자·최대 10개 (서버 검증, 로그 기록 금지)
- 예산은 서버가 유저의 `budget_plans` 에서 조회 — 없으면 `409 BUDGET_PLAN_REQUIRED`
- rate limit: 유저 5회/분 (`429 RATE_LIMITED`)
- LLM 실패 시 서버 내부 규칙 기반 폴백 생성, 폴백까지 실패 시에만 `status=failed`
- **v1.5**: 동기 `201` → **`202 Accepted`** 로 전환. 생성은 백그라운드 수행, 완료/실패 시 등록 디바이스에 푸시 발송

```json
// 202 MealPlanAcceptedResponse
{ "id": "uuid", "status": "processing" }
```
- 클라이언트(웹/앱 공통)는 `GET /mealplans/{id}` 를 폴링(3초 간격, 점진 백오프, 최대 3분)해 완료 확인 — **푸시는 보조 채널, 화면 폴링이 기본**
- 이미 `processing` 인 플랜이 있으면 `409 MEALPLAN_GENERATING` (중복 생성 방지)
- **v1.5.1 (QA BUG-001)**: `processing` 이 `MEALPLAN_GENERATION_TIMEOUT_MINUTES`(기본 10분) 초과 시 서버가 failed 로 수렴시킨다 — 접수·조회 경로에서 지연 정리 (좀비 processing 의 영구 409 방지)

```json
// (참고) 완료 후 GET 이 반환하는 MealPlanResponse
{
  "id": "uuid", "status": "ready",            // processing | ready | over_budget | failed  (v1.5 확장)
  "region": "KR", "currency": "KRW",
  "periodStart": "2026-07-09", "periodEnd": "2026-07-15",
  "budgetSummary": {
    "budget":      { "amount": "700000.00", "currency": "KRW" },
    "plannedCost": { "amount": "612300.00", "currency": "KRW" },
    "remaining":   { "amount": "87700.00",  "currency": "KRW" },
    "withinBudget": true
  },
  "meals": [ { "id": "uuid", "planDate": "2026-07-09", "mealType": "breakfast",
    "recipeName": "계란볶음밥",
    "ingredients": [ { "id": "uuid", "name": "계란", "quantity": "4", "unit": "ea",
      "estCost": { "amount": "2000.00", "currency": "KRW" } } ] } ],
  "notes": []
}
```
- `status=over_budget` 시 `withinBudget=false` + `notes` 에 초과 사유 — 프론트는 초과 배너 + 재생성 유도 (FR-206)
- **status 별 응답 규칙 (v1.5)**: `processing`/`failed` 는 `meals: []`, `budgetSummary: null`, `periodStart/End: null`. `failed` 는 `notes` 에 사유 코드(`GENERATION_FAILED`)

### 3-3. `GET /api/v1/mealplans/{id}` — 인증 필요 **(v1.5 — 생성 상태 폴링 겸용)**
- `200` MealPlanResponse (status 4종) / `404 NOT_FOUND` / `403 FORBIDDEN`(타인 소유)
- 읽기 전용 — rate limit 미적용 (폴링 용도). 별도 `/status` 엔드포인트는 만들지 않는다 (기존 상세 조회 재사용)

### 3-4. `PUT /api/v1/mealplans/{planId}/meals/{mealId}/completion` — 인증 필요 (v1.4 신규)
식사 완료 설정/해제. body `{ "completed": true|false }` → `200` 갱신된 MealOut. 404 NOT_FOUND / 403 FORBIDDEN(타인 소유).

**MealOut 확장 (v1.4, 하위 호환 옵셔널)**: `steps: string[]`(조리 단계), `completedAt: datetime|null`, `timeMinutes: int|null`, `difficulty: "easy"|"normal"|"hard"|null` — time/difficulty 는 신규 생성분부터 LLM 이 채움(부재 시 프론트 기본값).

### 3-5. `POST /api/v1/mealplans/{id}/regenerate` — 인증 필요 **(v1.5 변경 — 비동기 전환, v1.5.1 증보)**
```json
{ "scope": "all" }   // all | meal (meal 이면 mealId 필수 — 프론트 P2)
```
- rate limit 유저 5회/분. **`202 MealPlanAcceptedResponse`** (3-2 와 동일 패턴 — 폴링·완료 푸시 동일)
- **v1.5.1**: meals 0 인 failed 플랜(최초 생성부터 실패)은 원 요청 파라미터를 알 수 없어 재생성 불가 → `409 MEALPLAN_REGENERATE_EMPTY`. **프론트는 이 코드 수신 시 신규 `POST /mealplans` 흐름(생성 시트)으로 전환** (QA BUG-002 — 조용한 mealsPerDay 붕괴 제거)
- **v1.5.1**: 재생성 접수 시 서버가 플랜 `createdAt` 을 갱신 → 해당 플랜이 `GET /mealplans/latest` 의 최신이 된다 (stale 오판 방지 겸)

### 3-6. `GET /api/v1/mealplans/latest` — status 분기 (v1.5 규칙 추가)
- 최신 1건을 status 무관 반환 — 프론트 분기: `processing` → 생성 중 화면 / `failed` → 재시도 배너 / `ready·over_budget` → 기존 표시


---

## 4. household 도메인 (v1.2 신규 — 온보딩)

### 4-1. `PUT /api/v1/households/me` — 인증 필요
구성원 전체 교체 저장 (replace-all).
```json
{ "members": [ { "memberType": "adult_m", "age": 35 }, { "memberType": "toddler", "age": 4 } ] }
```
- `memberType ∈ adult_m|adult_f|teen|child|toddler`, 나이 범위 서버 재검증(성인 20~99/청소년 13~19/어린이 7~12/유아 0~6), 1~10명
- `200 { "members": [...], "size": 2 }`. household+budget_plan 모두 존재하게 되면 서버가 `onboarding_completed_at` 세팅
- 프리셋·기본 나이(성인남 35/성인여 33/청소년 15/어린이 9/유아 4)는 프론트 상수

### 4-2. `GET /api/v1/households/me` — 인증 필요
- `200` 위 구조 / `404 HOUSEHOLD_NOT_FOUND`

## 5. budget 확장 (v1.2)

### 5-1. `PUT /api/v1/budget/plans` — 인증 필요 (온보딩·수정용 upsert)
```json
{ "householdSize": 5, "budget": { "amount": "450000", "currency": "KRW" },
  "mealDirection": "health", "locked": true,
  "cuisines": ["korean", "japanese"] }
```
- `cuisines ∈ korean|western|japanese|chinese|comfort|salad` (0~6개), `locked` boolean
- 없으면 생성 `201`, 있으면 갱신 `200`. 검증은 POST 와 동일 + 확장 필드
- 기존 `POST /budget/plans`(게스트 이전)는 유지 — locked 기본 true, cuisines 기본 []
- 예산 슬라이더 기준(프론트 상수): KR 1인 최소 ₩80,000·권장 ₩130,000·최대 ₩220,000 / US $60·$100·$170

---

## 6. store 연동 상태 (v1.3 신규 — 설정 페이지, 실연동 아님)

### 6-1. `GET /api/v1/stores/connections` — 인증 필요
KR 4종 전체 상태 반환 (미저장 스토어는 disconnected).
```json
{ "connections": [ { "store": "kurly", "status": "connected", "connectedAt": "2026-07-10T00:00:00Z" },
                   { "store": "coupang", "status": "disconnected", "connectedAt": null } ] }
```

### 6-2. `PUT /api/v1/stores/connections/{store}` — 인증 필요
`store ∈ kurly|coupang|ssg|naver`(그 외 404 STORE_NOT_SUPPORTED). body `{ "connected": true|false }` → 200 (upsert).
> 1단계: 연동 상태 관리만(자격증명 미수집). 실계정 연동·자동 결제는 store 본설계에서 확장.

---

## 6-A. notification 도메인 (v1.5 신규)

> 대상 기획: `docs/기획/앱-웹뷰-푸시알림.md`. 발송 인프라는 Expo Push Service (KR/US 공통).
> **원칙 예외 명시**: 푸시 제목/본문은 백엔드가 사용자 로캘(ko/en) 템플릿으로 렌더해 발송한다 — "API 응답에 노출 문구 미포함" 원칙은 HTTP 응답에만 적용 (UI 대변인 합의).

### 6-A-1. `PUT /api/v1/notifications/devices` — 인증 필요
디바이스 토큰 등록/갱신 (token 기준 idempotent upsert — 앱 실행 시마다 호출해 `lastSeenAt`·locale·timezone 최신화).
```json
// 요청 DeviceRegisterRequest
{ "token": "ExponentPushToken[xxx]", "platform": "ios",    // ios | android
  "locale": "ko", "timezone": "Asia/Seoul", "appVersion": "1.0.0" }
```
- 검증: token 최대 4096자·Expo 토큰 형식, platform 열거, timezone 은 IANA 유효값, locale `ko|en`
- 타 유저에 등록돼 있던 token 이면 소유자를 현재 유저로 이전(기기 양도/계정 전환 케이스)
- `200 { "id": "uuid" }` / rate limit 유저 10회/분

### 6-A-2. `DELETE /api/v1/notifications/devices/{token}` — 인증 필요
로그아웃/알림 전체 해제 시 토큰 삭제. token 은 URL 인코딩. 본인 소유만 삭제(CWE-639), 없는 토큰도 `204` (idempotent).

### 6-A-3. `GET /api/v1/notifications/settings` — 인증 필요
```json
// 200 NotificationSettingsResponse
{ "settings": [
  { "type": "meal_reminder_breakfast", "enabled": true,  "localTime": "08:00", "timezone": "Asia/Seoul" },
  { "type": "meal_reminder_lunch",     "enabled": true,  "localTime": "12:00", "timezone": "Asia/Seoul" },
  { "type": "meal_reminder_dinner",    "enabled": true,  "localTime": "18:30", "timezone": "Asia/Seoul" },
  { "type": "mealplan_done",           "enabled": true,  "localTime": null,    "timezone": null },
  { "type": "weekly_nudge",            "enabled": false, "localTime": null,    "timezone": null }
] }
```
- 설정 행이 없으면 이 호출에서 기본값으로 **lazy 생성** 후 반환. timezone 기본값은 최근 등록 디바이스의 timezone
- `weekly_nudge`(식단 부재 유도, 주 1회 한도)는 P2 — 스키마만 선확정, 기본 off

### 6-A-4. `PUT /api/v1/notifications/settings` — 인증 필요
부분 갱신 — 보낸 type 만 반영.
```json
{ "settings": [ { "type": "meal_reminder_dinner", "enabled": true, "localTime": "19:00" } ] }
```
- 검증: type 열거, `localTime` HH:MM (리마인더 3종만 허용, 그 외 type 에 localTime 오면 422), timezone IANA
- 갱신 시 서버가 `next_send_at`(UTC) 재계산. `200` 전체 settings 재반환 / rate limit 유저 10회/분

### 6-A-5. 푸시 페이로드 규약 (프론트/앱 계약)
```json
{ "title": "...", "body": "...",                       // 백엔드 ko/en 템플릿 렌더
  "data": { "v": 1, "path": "/mealplan/{id}" } }      // path: 내부 상대경로 화이트리스트만 (CWE-601)
```
- 템플릿 키: `push.mealplanDone` (변수 없음) / `push.mealReminder` (변수: mealType, recipeName) / `push.mealplanFailed` / `push.weeklyNudge`
- 본문에 예산액·가구 구성 등 개인정보 금지 — 메뉴명까지만 (CWE-359, 잠금화면 노출 전제)

---

## 7. 엔드포인트 요약

| # | 메서드·경로 | 인증 | 유형 |
|---|-------------|------|------|
| 1 | `GET /api/v1/auth/{provider}/authorize` | 불필요 | 302 리다이렉트 |
| 2 | `GET /api/v1/auth/{provider}/callback` | 불필요 | 302 리다이렉트 |
| 3 | `POST /api/v1/auth/refresh` | refresh 쿠키 | JSON |
| 4 | `POST /api/v1/auth/logout` | 필요 | JSON |
| 5 | `GET /api/v1/users/me` | 필요 | JSON |
| 6 | `POST /api/v1/budget/plans` | 필요 | JSON |
| 7 | `GET /api/v1/mealplans/latest` | 필요 | JSON (v1.1 신규) |
| 8 | `POST /api/v1/mealplans` | 필요 | JSON |
| 9 | `GET /api/v1/mealplans/{id}` | 필요 | JSON |
| 10 | `POST /api/v1/mealplans/{id}/regenerate` | 필요 | JSON |
| 11 | `PUT /api/v1/households/me` | 필요 | JSON (v1.2 신규) |
| 12 | `GET /api/v1/households/me` | 필요 | JSON (v1.2 신규) |
| 13 | `PUT /api/v1/budget/plans` | 필요 | JSON (v1.2 신규) |
| 14 | `GET /api/v1/stores/connections` | 필요 | JSON (v1.3 신규) |
| 15 | `PUT /api/v1/stores/connections/{store}` | 필요 | JSON (v1.3 신규) |
| 16 | `PUT /api/v1/mealplans/{planId}/meals/{mealId}/completion` | 필요 | JSON (v1.4 신규) |
| 17 | `GET /api/v1/auth/app/session` | 불필요 | 302 리다이렉트 (v1.5 신규) |
| 18 | `PUT /api/v1/notifications/devices` | 필요 | JSON (v1.5 신규) |
| 19 | `DELETE /api/v1/notifications/devices/{token}` | 필요 | JSON (v1.5 신규) |
| 20 | `GET /api/v1/notifications/settings` | 필요 | JSON (v1.5 신규) |
| 21 | `PUT /api/v1/notifications/settings` | 필요 | JSON (v1.5 신규) |

## 변경 이력
- 2026-07-14: **v1.5.1** — QA 수정 반영: `409 MEALPLAN_REGENERATE_EMPTY`(프론트 신규 POST 전환), processing 타임아웃 수렴(기본 10분), 재생성 시 createdAt 갱신→latest 동작 명시. UI 대변인 동의 완료
- 2026-07-14: **v1.5** — 앱 웹뷰 + 푸시 알림: notification 도메인 4종 + 앱 로그인(`client=app`·`/auth/app/session`) + **mealplan 생성/재생성 202 비동기 전환**(status 4종 확장, `GET /mealplans/{id}` 폴링 겸용, `409 MEALPLAN_GENERATING` 신규) + 푸시 페이로드 규약(6-A-5). UI 대변인 동의 완료
- 2026-07-10: **v1.4** — 식사 완료 API + MealOut 확장(steps/completedAt/timeMinutes/difficulty). UI 대변인 동의
- 2026-07-10: **v1.3** — store 연동 상태 2종 (설정 페이지, 자격증명 미수집 1단계). UI 대변인 동의
- 2026-07-09: **v1.2** — household 도메인(PUT/GET /households/me) + PUT /budget/plans(locked·cuisines 확장). 온보딩 3스텝(프로토타입 1:1) 대응. UI 대변인 동의 완료
- 2026-07-09: **v1.1** — mealplan 도메인 정식 편입(구현 기준: camelCase/uuid/allergies·preferences 요청 필드) + `GET /mealplans/latest` 신규. 팀원 미머지 초안(cbd0623)의 상이점은 구현 우선으로 조정. UI 대변인 동의 완료
- 2026-07-09: v1 최초 확정 — 공통 규격(camelCase/에러/금액/페이지네이션) + auth 5종 + budget 1종. UI 대변인 동의 완료
