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

### 1-6. `PUT /api/v1/users/me/region` — 인증 필요 (v1.5 신규)
지역(국가) **수동 전환**. `country` 만 받고 **currency 는 서버가 매핑**(KR→KRW, US→USD)해 저장한다 — 클라이언트가 보낸 currency 는 무시(통화·국가 정합 강제).

```json
// 요청 UserRegionUpdateRequest
{ "country": "US" }        // KR | US (그 외 422)
```

| HTTP | 내용 |
|------|------|
| `200` | `UserMeResponse` (country/currency 갱신 반영 — 1-5 와 동일 구조) |
| `422 VALIDATION_ERROR` | country 열거 위반 |

- **소급 변환 없음(FR-606)**: 기존 `budget_plans`·`meal_plans` 의 저장 통화는 그대로 유지. 전환은 이후 **신규 데이터**(예산안/온보딩 통화 기본값)와 **표시**(글로벌 배지·스토어 세트)에만 적용. 프론트는 전환 시 "기존 플랜은 기존 통화로 유지" 안내 표시
- 본인 스코프 — 경로에 user_id 없음, 인증 유저 자신만 (CWE-639)
- users 리소스지만 계정 도메인이므로 **auth 도메인 라우터**에서 제공(GET /users/me 와 동일 위치)

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

### 3-4. `PUT /api/v1/mealplans/{planId}/meals/{mealId}/completion` — 인증 필요 (v1.4 신규)
식사 완료 설정/해제. body `{ "completed": true|false }` → `200` 갱신된 MealOut. 404 NOT_FOUND / 403 FORBIDDEN(타인 소유).

**MealOut 확장 (v1.4, 하위 호환 옵셔널)**: `steps: string[]`(조리 단계), `completedAt: datetime|null`, `timeMinutes: int|null`, `difficulty: "easy"|"normal"|"hard"|null` — time/difficulty 는 신규 생성분부터 LLM 이 채움(부재 시 프론트 기본값).

### 3-5. `POST /api/v1/mealplans/{id}/regenerate` — 인증 필요 (기존, 프론트 P1)
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

## 6. store 연동 상태 (v1.3 신규 / v1.5 국가별 확장 — 설정 페이지, 실연동 아님)

스토어 세트는 **`user.country` 기준**으로 분기한다 (FR-603).

| country | 스토어 세트 |
|---------|-------------|
| `KR` | `kurly` · `coupang` · `ssg` · `naver` |
| `US` | `walmart` · `instacart` |

### 6-1. `GET /api/v1/stores/connections` — 인증 필요
`user.country` 의 스토어 세트 전체 상태 반환 (미저장 스토어는 disconnected). 타 국가 스토어의 기존 연동 행은 **삭제하지 않고 응답에서 제외만** 한다 — 지역 재전환 시 이전 연동 상태 복원.
```json
{ "connections": [ { "store": "kurly", "status": "connected", "connectedAt": "2026-07-10T00:00:00Z" },
                   { "store": "coupang", "status": "disconnected", "connectedAt": null } ] }
```

### 6-2. `PUT /api/v1/stores/connections/{store}` — 인증 필요
`store` 는 **`user.country` 의 허용 세트**에 속해야 함(그 외 404 `STORE_NOT_SUPPORTED`). body `{ "connected": true|false }` → 200 (upsert).
> 1단계: 연동 상태 관리만(자격증명 미수집). 실계정 연동·자동 결제(US Walmart/Instacart 공식 API 포함)는 store 본설계에서 확장.

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
| 14 | `GET /api/v1/stores/connections` | 필요 | JSON (v1.3 / v1.5 국가별) |
| 15 | `PUT /api/v1/stores/connections/{store}` | 필요 | JSON (v1.3 / v1.5 국가별) |
| 16 | `PUT /api/v1/mealplans/{planId}/meals/{mealId}/completion` | 필요 | JSON (v1.4 신규) |
| 17 | `PUT /api/v1/users/me/region` | 필요 | JSON (v1.5 신규) |

## 9. cycle 도메인 (v1.8 신규 — 루프완결-주간사이클)

> 기획: `docs/기획/루프완결-주간사이클.md` 7장. camelCase, 금액 `Money`(문자열 amount + currency), 시각 ISO-8601 UTC.
>
> **문서 정합 안내**: 본 절은 `feature/auto-order-p0`(§7 order 도메인, v1.6) 와 `feature/app-webview-push`(§6-A notification, v1.5) 가 머지된 상태를 전제한다. 두 브랜치가 독립 번호를 쓴 탓에 본 증분은 충돌을 피해 **v1.8 / §9~§12** 를 사용한다. 머지 시 절 번호 정리는 문서 에이전트 소관.
>
> 공통: 경로에 `user_id` 없음 — 인증 유저 본인 행만 (CWE-639). 설정 행이 없으면 **최초 호출 시 기본값으로 lazy 생성**한다(notification 설정과 동일 패턴) — 따라서 `404 CYCLE_NOT_FOUND` 는 존재하지 않는다.

### 공통 타입 — `CycleState`

세 엔드포인트가 모두 같은 객체를 반환한다(GET/PUT/POST 응답 동형 — 프론트가 한 훅으로 상태를 갱신할 수 있게).

```json
{
  "enabled": true,
  "frequency": "weekly",
  "anchorWeekday": 0,
  "timezone": "Asia/Seoul",
  "autoConfirm": true,
  "cycleStart": "2026-09-06",
  "cycleDays": 7,
  "stage": "drafted",
  "nextRunAt": "2026-09-04T00:00:00Z",
  "skippedCycleStart": null,
  "weeklyLimit": { "amount": "112903.23", "currency": "KRW" },
  "mealPlan":   { "id": "uuid", "status": "ready" },
  "draftOrder": {
    "id": "uuid",
    "status": "draft",
    "estimatedTotal": { "amount": "58200.00", "currency": "KRW" },
    "autoConfirmAt": "2026-09-05T00:00:00Z",
    "blockedReason": null,
    "deliveryEta": null
  },
  "simulation": true
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `frequency` | `weekly \| biweekly` | 주기 프로파일 |
| `anchorWeekday` | int 0~6 | **0=일요일 … 6=토요일** (JS `Date.getDay()` 규약) |
| `timezone` | string | IANA. 서버가 화이트리스트 검증 |
| `cycleStart` | date (`YYYY-MM-DD`) | 현재 사이클의 배송 기준일(사용자 로컬). **멱등 키** |
| `cycleDays` | int | 사이클 길이 (weekly=7, biweekly=3\|4) |
| `stage` | enum(아래) | **파생값** — `last_stage` + 최신 주문/식단 상태로 서버가 계산. 홈 카드가 이 값 하나로 분기한다 |
| `nextRunAt` | datetime\|null | 다음 스케줄러 트리거 시각(UTC). 표시는 프론트가 로컬 변환 |
| `skippedCycleStart` | date\|null | 건너뛰기 처리된 사이클 (= `skip_until`) |
| `weeklyLimit` | Money | 이번 사이클 예산 한도 (architecture 3-9-4 안분기 결과, 음수는 0) |
| `mealPlan` | object\|null | 이번 사이클의 최신 식단 요약. 없으면 null |
| `draftOrder` | object\|null | `draft`/`awaiting_user` 주문 요약. 없으면 null |
| `simulation` | boolean | **항상 `true`** — 실결제 아님을 계약 레벨에서 고정 (US-814) |

`stage` 열거 (프론트는 이 값 → `cycle.stage.*` i18n 키로 매핑):

| 값 | 의미 |
|----|------|
| `idle` | 아직 이번 사이클 단계가 진행되지 않음 |
| `generating` | 식단 생성 중 (plan.status=`processing`) |
| `generated` | 식단 준비됨 |
| `generate_failed` | 식단 생성 실패 (수동 생성 CTA) |
| `drafted` | 초안 준비됨 — 승인 대기 (자동확정 예정) |
| `awaiting_user` | 게이트 차단 — 사용자 승인 필요 (`draftOrder.blockedReason` 참조) |
| `confirmed` | 확정됨 — 배송 대기 |
| `delivered` | 냉장고 등록 완료 — 이번 주 진행 중 |
| `nothing_to_order` | 냉장고가 전부 충당해 살 게 없음 (알림 발송 안 함) |
| `skipped_user` | 사용자가 이번 사이클 건너뛰기 |
| `skipped_dormant` | 휴면 판정으로 자동 생성 건너뜀 → 홈이 복귀 카드 노출 (FR-818) |
| `deferred_quota` | 일일 생성 상한 도달, 익일 이월 — **실패 아님** |
| `paused` | `enabled=false` |

`draftOrder.blockedReason` 열거: `BUDGET_EXCEEDED` · `UNMATCHED_RATIO` · `STORE_DISCONNECTED` · `AUTO_CONFIRM_OFF` · `US_NO_PRICE` · `MEALPLAN_OVER_BUDGET` (프론트가 `cycle.blocked.*` 로 매핑)

### 9-1. `GET /api/v1/cycle` — 인증 필요 (v1.8 신규)

내 사이클 상태. 설정 행이 없으면 기본값으로 생성 후 반환. 리미터 없음(읽기).

| HTTP | 내용 |
|------|------|
| `200` | `CycleState` |
| `401 AUTH_REQUIRED` | 공통 |

- 예산안이 없는 사용자(`BUDGET_PLAN_REQUIRED` 대상)는 **409 를 내지 않는다** — `weeklyLimit: null` 로 반환하고 홈이 예산 설정 CTA 를 띄운다. 홈 진입 API 가 409 를 내면 화면이 멈춘다.
- 성능 목표 p95 < 300ms. 내부 조회는 설정 1행 + 최신 식단 1행 + 열린 주문 1행 + 확정 합계 1건.

### 9-2. `PUT /api/v1/cycle/settings` — 인증 필요 (v1.8 신규)

부분 갱신(보낸 필드만 반영). `extra='forbid'`.

```json
{ "enabled": true, "frequency": "weekly", "anchorWeekday": 0, "timezone": "Asia/Seoul", "autoConfirm": true }
```

| 필드 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `enabled` | boolean\|null | | false = 사이클 일시정지 |
| `frequency` | `weekly \| biweekly` \| null | 열거 | **US 기본은 `weekly`** — biweekly 선택은 막지 않되 UI 가 권장 문구 표시 |
| `anchorWeekday` | int\|null | 0~6 | |
| `timezone` | string\|null | **IANA 화이트리스트**(`zoneinfo.available_timezones()`) | CWE-20 |
| `autoConfirm` | boolean\|null | | false = 항상 사용자 승인 |

| HTTP | code | 상황 |
|------|------|------|
| `200` | — | `CycleState` (재계산된 `nextRunAt` 포함) |
| `401` | `AUTH_REQUIRED` | 공통 |
| `422` | `VALIDATION_ERROR` | 열거·범위·타임존 위반, 또는 extra 필드 |
| `429` | `RATE_LIMITED` | 유저 기준 **5회/분** |

- **변경 시 부작용**: `frequency`/`anchorWeekday`/`timezone` 이 바뀌면 `nextRunAt` 을 즉시 재계산한다(DST·타임존 이동 대응). `autoConfirm=false` 로 바꾸면 열린 초안의 `autoConfirmAt` 을 **NULL 로 지운다**(예약된 자동확정이 살아 있으면 설정이 거짓말이 된다). 다시 `true` 로 바꾸면 열린 초안에 `초안 생성시각 + graceHours` 를 재설정하되, 이미 지난 시각이면 `now + 1시간` 으로 둔다.
- `enabled=false` → 스케줄러 스캔 ①에서 제외(partial index 조건). 이미 만들어진 초안은 그대로 두고 자동확정만 멈춘다(`autoConfirmAt=NULL`).

### 9-3. `POST /api/v1/cycle/skip` — 인증 필요 (v1.8 신규)

이번 사이클 **1회만** 건너뛴다. body 없음(대상은 항상 현재 `cycleStart` — 클라이언트가 대상 사이클을 지정하게 하면 과거 사이클 조작 표면이 생긴다).

| HTTP | code | 상황 |
|------|------|------|
| `200` | — | `CycleState` (`stage='skipped_user'`, `skippedCycleStart=cycleStart`) |
| `401` | `AUTH_REQUIRED` | 공통 |
| `409` | `CYCLE_ALREADY_CONFIRMED` | 이번 사이클에 이미 확정 주문이 있음 → 건너뛰기 대신 `POST /orders/{id}/cancel` 안내 |
| `429` | `RATE_LIMITED` | **5회/분** |

- **멱등**: 이미 같은 사이클을 스킵했으면 그대로 `200`.
- 부작용: 열린 초안이 있으면 `status='cancelled'`, `auto_confirm_at=NULL`. 다음 사이클은 정상 진행한다(설정을 끄지 않는다).

---

## 10. order 도메인 확장 (v1.8 — 사이클 편입)

> §7(v1.6, auto-order-p0)의 계약 위에 얹는다. **아래 10-4 는 기존 계약을 확장하는 변경**이므로 프론트 영향도를 별도 표기한다.

### `OrderResponse` 확장 필드 (v1.8)

기존 필드(`id`·`store`·`status`·`frequency`·`nextSuggestedAt`·`estimatedTotal`·`confirmedAt`·`simulation`·`items`)는 **전부 유지**하고 아래를 추가한다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `cycleStart` | date | 이 주문이 속한 사이클 |
| `deliveryEta` | datetime\|null | 배송 예정(UTC). 초안은 null |
| `inboundAt` | datetime\|null | 냉장고 등록 완료 시각 |
| `deliveryState` | `pending \| delivered \| unknown` | 배송 확인 상태 (`status` 와 별개 축) |
| `deliveryConfirmAttempts` | int | "아직 안 왔어요" 누적 |
| `autoConfirmed` | boolean | 그레이스 자동확정으로 확정됐는지 |
| `autoConfirmAt` | datetime\|null | 자동확정 예정 시각. **null = 자동확정 안 함** |
| `blockedReason` | string\|null | `awaiting_user` 사유 코드 |

- `confirmedAt` 은 초안 단계에서 **null 이 될 수 있다** — v1.6 은 `confirmed` 단일 상태였으므로 non-null 이었다. **계약 변경 지점**(10-4 참조).

### 10-1. `POST /api/v1/orders/{id}/approve` — 인증 필요 (v1.8 신규)

초안을 승인해 확정한다. **서버가 preview 를 재계산**한다 — 클라이언트가 보낸 라인·가격·`matched` 를 받지 않는다 (CWE-602).

```json
// 요청 (선택). 라인/가격 필드 없음 — 보내면 422
{ "excludeNames": ["양파"] }
```

| 필드 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `excludeNames` | string[] \| null | 0~40개, 각 1~200자 | **P1** — 승인 시 제외할 needed 품목명. 서버는 재계산 결과에서 **이름만** 필터링하며 가격·수량은 여전히 서버 값을 쓴다(CWE-602 위반 아님). P0 구현에서는 무시하고 422 를 내지 않는다 |

- `extra='forbid'`. `store` 는 body 로 받지 않는다 — 초안 행의 `store` 를 쓴다(초안 생성 시 서버가 결정).
- 확정 시 서버가 부여: `status='confirmed'`, `auto_confirmed=false`, `confirmed_at=now`, `delivery_eta`(architecture 3-9-9), `auto_confirm_at=NULL`, `simulation=true`.
- **냉장고에 즉시 넣지 않는다** — inbound 는 `delivery_eta` 시점(스케줄러 스캔 ③). v1.6 의 "확정 즉시 inbound" 동작에서 바뀐 지점이다.

| HTTP | code | 상황 |
|------|------|------|
| `200` | — | `OrderResponse` (확정 스냅샷) |
| `401` | `AUTH_REQUIRED` | 공통 |
| `403` | `FORBIDDEN` | 타인 주문 |
| `404` | `ORDER_NOT_FOUND` | |
| `404` | `MEALPLAN_NOT_FOUND` | 재계산 시 최신 식단 없음 |
| `409` | `ORDER_INVALID_STATE` | `draft`/`awaiting_user` 가 아님 |
| `409` | `ORDER_ALREADY_CONFIRMED` | 이 사이클에 확정 주문이 이미 있음 (부분 유니크 위반 — 멱등) |
| `422` | `STORE_NOT_CONNECTED` | 초안의 store 연동이 풀림 |
| `422` | `NOTHING_TO_ORDER` | 재계산 결과 needed 없음(또는 전부 제외됨) |
| `422` | `VALIDATION_ERROR` | extra 필드, `excludeNames` 제약 위반 |
| `429` | `RATE_LIMITED` | **5회/분** |

> **재계산의 대가(명시)**: 승인 시점의 냉장고·식단·시세가 초안 생성 시점과 다르면 **확정 라인이 초안 화면과 달라질 수 있다.** 프론트는 확정 **응답**을 그대로 표시하고, 초안 캐시로 결과를 그리지 않는다. 이는 CWE-602 를 지키기 위한 의도된 트레이드오프다.

### 10-2. `POST /api/v1/orders/{id}/cancel` — 인증 필요 (v1.8 신규)

확정 주문을 취소한다. body 없음.

| HTTP | code | 상황 |
|------|------|------|
| `200` | — | `OrderResponse` (`status='cancelled'`) |
| `401` | `AUTH_REQUIRED` | 공통 |
| `403` | `FORBIDDEN` | 타인 주문 |
| `404` | `ORDER_NOT_FOUND` | |
| `409` | `ORDER_INVALID_STATE` | `confirmed` 가 아님 |
| `409` | `ORDER_CANCEL_WINDOW_CLOSED` | `cycleStart + CYCLE_CANCEL_WINDOW_DAYS`(기본 7일) 경과 |
| `429` | `RATE_LIMITED` | **5회/분** |

- **냉장고 롤백**: `inboundAt` 이 있으면 `fridge_items WHERE order_id = :id` 중 **남아 있는 행만** 삭제한다. 이미 식사 완료로 차감된 분은 되돌리지 않는다(음수 재고 금지). `inboundAt` 은 감사 이력으로 남긴다.
- 취소 후 같은 사이클에 재확정이 가능하다 — 부분 유니크 인덱스는 `status='confirmed'` 만 대상이기 때문이다(의도된 동작).
- 실결제 도입 후에는 스토어 취소 마감 시각이 추가 조건이 된다 (이번 범위 밖).

### 10-3. `POST /api/v1/orders/{id}/delivery` — 인증 필요 (v1.8 신규)

배송 도착 여부를 사용자가 보정한다 (기획 5-3).

```json
{ "received": true }
```

| `received` | 동작 |
|------------|------|
| `true` | 아직 등록 전이면 **즉시 등록**(compare-and-set → needed 라인 inbound), `deliveryState='delivered'`. 이미 등록됐으면 상태만 확정하고 no-op |
| `false` | 등록됐으면 `order_id` 기준 롤백 + `inboundAt=NULL`, `deliveryEta += 1일`, `deliveryConfirmAttempts += 1`. 누적이 `CYCLE_DELIVERY_UNKNOWN_ATTEMPTS`(기본 3) 에 도달하면 `deliveryState='unknown'` 으로 자동 등록을 중단한다 |

| HTTP | code | 상황 |
|------|------|------|
| `200` | — | `OrderResponse` |
| `401` | `AUTH_REQUIRED` | 공통 |
| `403` | `FORBIDDEN` | 타인 주문 |
| `404` | `ORDER_NOT_FOUND` | |
| `409` | `ORDER_INVALID_STATE` | `confirmed` 가 아님 |
| `422` | `VALIDATION_ERROR` | body 누락/extra 필드 |
| `429` | `RATE_LIMITED` | **5회/분** |

- `deliveryState='unknown'` 상태에서 `received=true` 를 누르면 등록되고 `delivered` 로 복귀한다. **다음 사이클 초안은 이 주문이 냉장고에 없다는 전제로 계산된다**(등록되지 않았으므로 자연히 그렇게 된다 — 과소 발주 방지).

### 10-4. `GET /api/v1/orders/latest` — **계약 확장 (v1.8, 하위호환 주의)**

| 구분 | v1.6 | v1.8 |
|------|------|------|
| `status` | `confirmed` 만 | `draft` · `awaiting_user` · `confirmed` · `cancelled` · `expired` · `failed` |
| `confirmedAt` | 항상 non-null | 초안 단계에서 **null** |
| 필드 | 9종 | +8종 (위 확장 필드) |

> **⚠ 기존 계약을 깨는 변경**입니다. v1.6 프론트(`features/order/OrdersController`)가 `status === 'confirmed'` 또는 `confirmedAt` non-null 을 가정하고 있으면 초안 상태에서 오동작합니다.
> **사유**: 사이클이 초안(draft)을 **저장된 주문 행**으로 만들기 때문에, "최신 주문"에 초안이 등장하는 것이 필연입니다. 별도 `/orders/draft` 를 만드는 대안은 "최신 주문"이 두 곳으로 갈라져 프론트가 두 API 를 합성해야 하므로 채택하지 않았습니다.
> **영향 범위**: UI 프론트엔드 — `/orders` 페이지 상태 분기 전면 확장(ui-design 14장), 홈 `AutoOrderCard`. **UI 대변인 동의 필요 항목**.

### 10-5. `GET /api/v1/orders/preview` — **계약 확장 (v1.8, 하위호환 O)**

기존 응답 필드는 전부 유지하고 아래를 **추가**한다(추가만이므로 v1.6 프론트는 그대로 동작).

| 필드 | 타입 | 설명 |
|------|------|------|
| `orderId` | uuid\|null | 저장된 초안이 있으면 그 id |
| `status` | `draft \| awaiting_user` \| null | 저장된 초안의 상태. null = 저장된 초안 없음(즉석 계산 결과) |
| `autoConfirmAt` | datetime\|null | 자동확정 예정 시각 |
| `blockedReason` | string\|null | `awaiting_user` 사유 |
| `cycleStart` | date | 현재 사이클 |

- **동작 변경**: 현재 사이클에 `draft`/`awaiting_user` 주문이 있으면 **재계산하지 않고 그 스냅샷을 반환**한다. 사용자가 화면을 열 때마다 네이버+LLM 을 호출하던 비용이 사라지고, 승인 화면이 흔들리지 않는다.
- 강제 재계산: `?refresh=true` — 초안을 최신 계산으로 **갱신 저장**한다. 기존 store 리미터 **3회/분** 유지.
- `refresh` 없이 저장된 초안이 없으면 기존 v1.6 동작(즉석 계산, 저장 안 함) 그대로.

### 10-6. `POST /api/v1/orders` — 변경 없음 (명시적 확정, v1.6 유지)

사용자가 사이클과 무관하게 직접 확정하는 경로로 유지한다. 단 서버가 `cycle_start` 를 현재 사이클로 채우므로 **부분 유니크 인덱스의 적용을 받는다**. 이 사이클에 이미 확정 주문이 있으면 `409 ORDER_ALREADY_CONFIRMED`(신규). 확정 즉시 inbound 하던 동작은 **제거**되고 `delivery_eta` 시점으로 옮겨진다.

---

## 11. 기타 확장·표기 (v1.8)

### 11-1. `GET/PUT /api/v1/notifications/settings` — 타입 3종 추가 (계약 확장, 하위호환 O)

| type | 기본 | 용도 |
|------|------|------|
| `order_approval` | on | 초안 준비됨 — 승인 요청 (FR-808) |
| `fridge_inbound` | on | 배송분 냉장고 등록 — 보정 유도 (FR-821) |
| `cycle_paused` | on | 휴면 전환 안내 (1회) |

- 응답 배열에 3개 항목이 늘어난다. 프론트가 알려진 type 만 렌더하면 하위호환된다.
- 세 타입 모두 `localTime`/`timezone` 은 **null**(리마인더가 아니므로 시각 설정 대상이 아님).
- **DB CHECK 재정의가 필요하다** — db-schema 2-13 (인계사항 7 확인 결과).
- 푸시 페이로드는 §6-A-5 규약을 그대로 따른다. 신규 `data.path` 화이트리스트: `/orders`, `/fridge` (CWE-601).
- **본문에 금액·예산액·가구 구성을 넣지 않는다** (CWE-359, 잠금화면 전제):

| template_key | ko | en |
|--------------|----|----|
| `push.orderApproval` | "이번 주 장바구니가 준비됐어요" / "확인해 주세요" | "Your weekly cart is ready" / "Take a look." |
| `push.fridgeInbound` | "받으셨나요? 냉장고에 담아둘게요" / "실제와 다르면 수정해 주세요" | "Did it arrive? We'll stock your fridge" / "Adjust it if anything's different." |
| `push.cyclePaused` | "잠시 자동 식단을 멈췄어요" / "언제든 다시 시작할 수 있어요" | "We paused your auto meal plans" / "You can resume anytime." |

### 11-2. `POST /api/v1/mealplans` — 202 비동기 (전제, 변경 없음)

`feature/app-webview-push` 의 v1.5 전환(`202 Accepted` + `GET /mealplans/{id}` 폴링)을 **그대로 승계**한다. 본 설계는 계약을 바꾸지 않으며, 자동 사이클이 `run_meal_plan_generation` 을 백그라운드로 호출하는 **전제 조건**으로만 의존한다.

- 자동 생성은 **HTTP 요청 없이** 스케줄러가 `start_meal_plan_generation` → `run_meal_plan_generation` 을 직접 호출한다. `mealplan_user_limiter`(5회/분)는 사용자 요청 경로에만 적용되며, 자동 경로는 FR-817 상한이 대신한다.

### 11-3. `POST /api/v1/mealplans/monthly` — **내부/실험용 (제품 흐름 비사용)** (인계사항 8)

기존 구현(`mealplan/router.py`)을 문서에 처음 편입하되, 아래를 명시한다.

| 항목 | 내용 |
|------|------|
| **분류** | **내부/실험용.** 제품 정본 사이클은 **주간 롤링**이며(기획 Q2), 회원 UI 는 이 엔드포인트를 호출하지 않는다(현재도 호출하지 않음) |
| **존치 이유** | 삭제하지 않는다. 월 예산 안분 계산이 주간 한도 산출의 기반이며, 실험·검증 경로로 유용하다 |
| **재배치** | 내부 `_prorate` 는 `budget.service.prorate_remaining_month` 로 이동한다(architecture 3-9-4). **결과값은 완전히 동일**하며 이 엔드포인트의 동작은 바뀌지 않는다 |
| 인증 / 리미터 | 인증 필요 / `store_user_limiter` **3회/분** (네이버+LLM) |
| 요청 | `{ "asOf": "2026-09-01", "mealsPerDay": 3, "cycle": "weekly" }` (전부 선택) |
| 응답 | `201 MonthlyPlanResponse` — 월 식단 + 첫 주기 주문 미리보기 |

> 신규 개발은 이 엔드포인트에 의존하지 않는다. 제거 여부는 주간 사이클 안정화 후 재평가한다.

### 11-4. 신규 공통 에러 코드 (v1.8)

| HTTP | code | 의미 |
|------|------|------|
| 409 | `ORDER_INVALID_STATE` | 요청한 전이가 현재 상태에서 허용되지 않음 (CWE-841) |
| 409 | `ORDER_ALREADY_CONFIRMED` | 이 사이클에 확정 주문이 이미 있음 (멱등 제약) |
| 409 | `ORDER_CANCEL_WINDOW_CLOSED` | 취소 허용 기간 경과 |
| 409 | `CYCLE_ALREADY_CONFIRMED` | 확정된 사이클은 건너뛸 수 없음 |

---

## 12. 엔드포인트 요약 — v1.8 증분

> 기존 요약 표(§8, v1.6 기준 21행)에 아래를 **이어 붙인다**. 번호는 머지 후 재부여한다.

| 메서드·경로 | 인증 | 유형 |
|-------------|------|------|
| `GET /api/v1/cycle` | 필요 | JSON (v1.8 신규) |
| `PUT /api/v1/cycle/settings` | 필요 | JSON (v1.8 신규) |
| `POST /api/v1/cycle/skip` | 필요 | JSON (v1.8 신규) |
| `POST /api/v1/orders/{id}/approve` | 필요 | JSON (v1.8 신규) |
| `POST /api/v1/orders/{id}/cancel` | 필요 | JSON (v1.8 신규) |
| `POST /api/v1/orders/{id}/delivery` | 필요 | JSON (v1.8 신규) |
| `POST /api/v1/mealplans/monthly` | 필요 | JSON (기존 구현, v1.8 문서 편입 — **내부/실험용**) |

**확장(기존 경로)**

| 메서드·경로 | 변경 | 하위호환 |
|-------------|------|----------|
| `GET /api/v1/orders/latest` | status 6종 확장 + 필드 8종 추가 + `confirmedAt` nullable | ⚠ **깨짐** — 10-4 |
| `GET /api/v1/orders/preview` | 초안 스냅샷 반환 + 필드 5종 추가 + `?refresh` | ✅ 추가만 |
| `POST /api/v1/orders` | `cycle_start` 부여 → 멱등 제약 적용, 확정 즉시 inbound 제거 | ⚠ 신규 409 |
| `GET/PUT /api/v1/notifications/settings` | type 3종 추가 | ✅ 추가만 |
| `POST /api/v1/mealplans` | 변경 없음 (v1.5 202 승계) | ✅ |

## 변경 이력
- 2026-08-30: **v1.8** — 주간 자동 사이클: cycle 도메인 3종(`GET /cycle`·`PUT /cycle/settings`·`POST /cycle/skip`) + order 3종(`approve`·`cancel`·`delivery`) 신규, `GET /orders/latest` **계약 확장(하위호환 깨짐 — 10-4 사유 기재)**, `GET /orders/preview` 초안 스냅샷(추가만), notification type 3종, `POST /mealplans/monthly` **내부/실험용** 표기. 신규 에러 4종. UI 대변인 동의 완료
- 2026-07-10: **v1.5** — 지역 전환 API(`PUT /users/me/region`, currency 서버 매핑·소급 변환 없음) + store 연동 국가별 세트 분기(KR 4 / US 2, walmart·instacart 편입). UI 대변인 동의
- 2026-07-10: **v1.4** — 식사 완료 API + MealOut 확장(steps/completedAt/timeMinutes/difficulty). UI 대변인 동의
- 2026-07-10: **v1.3** — store 연동 상태 2종 (설정 페이지, 자격증명 미수집 1단계). UI 대변인 동의
- 2026-07-09: **v1.2** — household 도메인(PUT/GET /households/me) + PUT /budget/plans(locked·cuisines 확장). 온보딩 3스텝(프로토타입 1:1) 대응. UI 대변인 동의 완료
- 2026-07-09: **v1.1** — mealplan 도메인 정식 편입(구현 기준: camelCase/uuid/allergies·preferences 요청 필드) + `GET /mealplans/latest` 신규. 팀원 미머지 초안(cbd0623)의 상이점은 구현 우선으로 조정. UI 대변인 동의 완료
- 2026-07-09: v1 최초 확정 — 공통 규격(camelCase/에러/금액/페이지네이션) + auth 5종 + budget 1종. UI 대변인 동의 완료
