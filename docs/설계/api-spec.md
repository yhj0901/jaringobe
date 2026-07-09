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

- 동작: 서명된 `state`(nonce + next + 10분 만료) 생성 → provider 인가 URL 로 302

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

> `GET/PUT /budget/plans` 등 조회·수정 API 는 budget 본설계에서 확정 (이번 범위 아님).

---

## 3. mealplan 도메인 (v1.1 — 구현 기준 정식 편입)

> 팀원 구현(PR #8)을 계약으로 정식화. 요청/응답은 camelCase, id 는 uuid, 금액은 Money(문자열+통화).

### 3-1. `GET /api/v1/mealplans/latest` — 인증 필요 **(v1.1 신규 — 백엔드 구현 필요)**
인증 유저의 가장 최근 식단 1건 (`created_at DESC LIMIT 1`, 기존 인덱스 `ix_meal_plans_user_created` 커버).

| HTTP | 내용 |
|------|------|
| `200` | `MealPlanResponse` (3-2 와 동일 구조) |
| `404 MEALPLAN_NOT_FOUND` | 생성 이력 없음 — 프론트 빈 상태 분기 전용 코드 |

### 3-2. `POST /api/v1/mealplans` — 인증 필요 (기존)
```json
// 요청 MealPlanCreateRequest
{ "days": 7, "mealsPerDay": 3, "allergies": ["땅콩"], "preferences": ["한식"] }
```
- `days` 1~31, `mealsPerDay` 1~5. `allergies`/`preferences` 는 항목당 30자·최대 10개 (서버 검증, 로그 기록 금지)
- 예산은 서버가 유저의 `budget_plans` 에서 조회 — 없으면 `409 BUDGET_PLAN_REQUIRED`
- rate limit: 유저 5회/분 (`429 RATE_LIMITED`)
- LLM 실패 시 서버 내부 규칙 기반 폴백 생성 (5xx 아님)

```json
// 201 MealPlanResponse
{
  "id": "uuid", "status": "ready",            // ready | over_budget
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

### 3-3. `GET /api/v1/mealplans/{id}` — 인증 필요 (기존)
- `200` MealPlanResponse / `404 NOT_FOUND` / `403 FORBIDDEN`(타인 소유)

### 3-4. `POST /api/v1/mealplans/{id}/regenerate` — 인증 필요 (기존, 프론트 P1)
```json
{ "scope": "all" }   // all | meal (meal 이면 mealId 필수 — 프론트 P2)
```
- rate limit 유저 5회/분. `200` 갱신된 MealPlanResponse


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

## 6. 엔드포인트 요약

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

## 변경 이력
- 2026-07-09: **v1.2** — household 도메인(PUT/GET /households/me) + PUT /budget/plans(locked·cuisines 확장). 온보딩 3스텝(프로토타입 1:1) 대응. UI 대변인 동의 완료
- 2026-07-09: **v1.1** — mealplan 도메인 정식 편입(구현 기준: camelCase/uuid/allergies·preferences 요청 필드) + `GET /mealplans/latest` 신규. 팀원 미머지 초안(cbd0623)의 상이점은 구현 우선으로 조정. UI 대변인 동의 완료
- 2026-07-09: v1 최초 확정 — 공통 규격(camelCase/에러/금액/페이지네이션) + auth 5종 + budget 1종. UI 대변인 동의 완료
