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

### 6-3. `POST /api/v1/store/cart` — 인증 필요 (기존 구현, v1.6 문서 편입)

경로 **단수** `/store/cart` (`/stores/connections` 복수와 구분). 재료 목록 → 네이버 쇼핑 검색 → LLM 선택. **자동주문 P0 는 프론트가 이 API 로 preview 를 우회하지 않는다** — order 서비스가 내부 `build_cart` 를 호출한다 (FR-714).

```json
// 요청 StoreCartRequest
{
  "items": [ { "name": "계란", "quantity": 10, "unit": "ea" } ],
  "mall": "kurly",
  "maxPages": 5
}
```

| 필드 | 타입 | 제약 | 기본 |
|------|------|------|------|
| `items` | `NeededItem[]` | 1~40 | (필수) |
| `items[].name` | string | 필수 | |
| `items[].quantity` | number\|null | **구현 기준 float** (기존 store 계약 유지) | null |
| `items[].unit` | string\|null | | null |
| `mall` | `kurly \| all` | | `kurly` |
| `maxPages` | int | 1~10 | `5` |

```json
// 200 StoreCartResponse
{
  "items": [
    { "ingredient": "계란", "matched": true, "title": "신선한 계란 10구",
      "price": { "amount": "5980.00", "currency": "KRW" },
      "mallName": "마켓컬리", "link": "https://...", "candidateCount": 12 }
  ],
  "total": { "amount": "5980.00", "currency": "KRW" },
  "matchedCount": 1,
  "notes": []
}
```

| HTTP | 내용 |
|------|------|
| `200` | `StoreCartResponse` |
| `401 AUTH_REQUIRED` | 인증 쿠키 없음/만료 |
| `422 VALIDATION_ERROR` | items 길이·mall 열거·maxPages 범위 위반 |
| `429 RATE_LIMITED` | 유저 기준 **3회/분** (`store_user_limiter`, CWE-770) |

- 네이버 키 없으면 items 전부 `matched=false`, total 0, notes 에 사유 (5xx 아님)
- 상품 `title` 은 네이버 HTML 태그 스트립. P0 KR 추정가는 이 어댑터를 **mall=`kurly` 고정**으로 재사용. 쿠팡/월마트 검색 API 를 만들지 않음


---

## 7. order 도메인 (v1.6 — 자동주문 P0)

> 기획: `docs/기획/자동주문-장바구니.md`. camelCase, 금액 Money(문자열+통화), 시각 ISO-8601 UTC.
> P0 는 **시뮬레이션 확정**만. `status=confirmed` (`paid` 도입 금지). 실 체크아웃·웹훅·취소/환불·게스트 주문·`GET /orders/{id}` 목록은 만들지 않음.

공통: 경로에 user_id 없음 — 인증 유저 본인 행만 (CWE-639). `GET /orders/latest` 는 `created_at DESC LIMIT 1`.

### 7-1. `GET /api/v1/orders/preview` — 인증 필요 (v1.6 신규)

서버가 최신 식단의 **미완료** 끼니 재료 합 − 냉장고 재고로 needed/covered 를 계산한다. 스토어 연동 여부와 무관하게 200. 매칭: `name.strip().lower()` + **단위 일치**. 냉장고에만 있는 재고는 목록 미등재.

- KR + `NAVER_CLIENT_ID/SECRET` 있으면 내부 `store.service.build_cart`(mall=`kurly`) 호출
- 키 없거나 US 이면 `cart.items` 를 needed 기준 `matched=false`, `total.amount="0.00"`, notes 에 사유. **US 네이버 호출 금지·가짜 USD 금지**
- `toBuy==0` 인 라인은 `needed` 가 아니라 `covered` 로만 둔다

```json
// 200 OrderPreviewResponse
{
  "mealPlanId": "uuid",
  "storeConnected": true,
  "country": "KR",
  "needed": [
    { "name": "계란", "unit": "ea", "needed": "12", "fromFridge": "2", "toBuy": "10" }
  ],
  "covered": [
    { "name": "양파", "unit": "ea", "needed": "3", "fromFridge": "3", "toBuy": "0" }
  ],
  "cart": {
    "items": [
      { "ingredient": "계란", "matched": true, "title": "신선한 계란 10구",
        "price": { "amount": "5980.00", "currency": "KRW" },
        "mallName": "마켓컬리", "link": "https://...", "candidateCount": 12 }
    ],
    "total": { "amount": "5980.00", "currency": "KRW" },
    "matchedCount": 1,
    "notes": []
  },
  "estimatedTotal": { "amount": "5980.00", "currency": "KRW" },
  "notes": []
}
```

| HTTP | 내용 |
|------|------|
| `200` | `OrderPreviewResponse` |
| `401 AUTH_REQUIRED` | 공통 |
| `404 MEALPLAN_NOT_FOUND` | 최신 식단 없음 |
| `429 RATE_LIMITED` | **3회/분** — 기존 store 리미터와 동일 스펙 재사용 (네이버+LLM 비용 방어, CWE-770) |

- 성능: 네이버 순차조회+LLM 이 붙을 수 있음 — 기존 store 한도(수 초~수십 초) 허용. 프론트 스켈레톤+aria-busy
- `cart.items[].link` 는 **https 만** 허용 (그 외 null, CWE-79)
- `storeConnected` 는 현재 country 세트 중 `status=connected` 가 1개 이상이면 true (preview 자체는 연동 없이 동작)

### 7-2. `POST /api/v1/orders` — 인증 필요 (v1.6 신규)

현재 preview 를 **서버가 재계산**해 mock 확정 주문을 저장한다. 클라이언트 라인·가격·matched 를 **받지 않음** (CWE-602). 프론트 preview 캐시로 확정 금지.

```json
// 요청 OrderCreateRequest — 라인 목록 필드 없음 (보내면 422 VALIDATION_ERROR)
{ "store": "kurly" }
```

- `store`: `user.country` 허용 세트 enum (KR: `kurly|coupang|ssg|naver`, US: `walmart|instacart`). 세트 밖 → 404 `STORE_NOT_SUPPORTED` (기존 연동 API 와 동일)
- **`extra='forbid'`** — `items` 등 추가 필드 시 422 `VALIDATION_ERROR`
- `status`/`frequency`/`lineType`/`simulation` 은 서버가 부여 (클라이언트 설정 불가). P0: `status=confirmed`, `frequency=weekly`, `simulation=true`
- 확정 전제: body.store 가 `store_connections.status=connected`. 미연동 → 422 `STORE_NOT_CONNECTED`
- 재계산 후 needed 가 비면 422 `NOTHING_TO_ORDER` (covered 만 있는 preview 는 GET 으로 표시 가능, POST 는 거절)
- 트랜잭션: 주문+라인 스냅샷 저장 후 **needed 수량만** `fridge.add_items(..., source="order")`. covered inbound 금지. `expires_at=null`. 프론트는 `POST /fridge/items` 를 이중 호출하지 않음

```json
// 201 OrderResponse (스냅샷)
{
  "id": "uuid",
  "store": "kurly",
  "status": "confirmed",
  "frequency": "weekly",
  "nextSuggestedAt": "2026-08-22T08:15:00Z",
  "estimatedTotal": { "amount": "5980.00", "currency": "KRW" },
  "confirmedAt": "2026-08-15T08:15:00Z",
  "simulation": true,
  "items": [
    { "name": "계란", "quantity": "10", "unit": "ea", "lineType": "needed",
      "matched": true, "title": "신선한 계란 10구",
      "unitPrice": { "amount": "5980.00", "currency": "KRW" } },
    { "name": "양파", "quantity": "3", "unit": "ea", "lineType": "covered",
      "matched": false, "title": null, "unitPrice": null }
  ]
}
```

- `nextSuggestedAt` = `confirmedAt` + 7일 (표시용, 스케줄러 잡 없음)
- `items[].quantity`: needed 면 toBuy, covered 면 fromFridge (문자열 Decimal)
- US/키없음: `estimatedTotal.amount="0.00"`, currency 는 유저 통화, 라인 `unitPrice=null`, `matched=false`
- 재확정 시 냉장고 인플레는 P0 에서 막지 않음 (멱등 키 P1). UI 경고 카피만

| HTTP | code | 상황 |
|------|------|------|
| `201` | — | `OrderResponse` |
| `401` | `AUTH_REQUIRED` | 공통 |
| `404` | `MEALPLAN_NOT_FOUND` | 재계산 시 최신 식단 없음 |
| `404` | `STORE_NOT_SUPPORTED` | body.store 가 현재 country 세트 밖 |
| `422` | `STORE_NOT_CONNECTED` | 해당 store 미연동 (또는 connected 0개) |
| `422` | `NOTHING_TO_ORDER` | 재계산 후 needed 없음 |
| `422` | `VALIDATION_ERROR` | store enum 위반, 또는 클라이언트가 items 등 extra 필드를 보냄 |
| `429` | `RATE_LIMITED` | 유저 기준 **5회/분** |

### 7-3. `GET /api/v1/orders/latest` — 인증 필요 (v1.6 신규)

해당 유저 최신 주문 1건 (`created_at DESC LIMIT 1`). 본인 스코프. 리미터 없음 (읽기).

| HTTP | 내용 |
|------|------|
| `200` | `OrderResponse` (7-2 와 동일 구조) |
| `401 AUTH_REQUIRED` | 공통 |
| `404 ORDER_NOT_FOUND` | 확정 이력 없음 |

**명시적으로 만들지 않는 API**: 결제 승인, 웹훅, 주문 취소/환불, 게스트 주문, `/orders/{id}` 목록 페이지네이션.

---

## 8. 엔드포인트 요약

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
| 18 | `POST /api/v1/store/cart` | 필요 | JSON (기존 구현, v1.6 문서 편입 — 경로 단수) |
| 19 | `GET /api/v1/orders/preview` | 필요 | JSON (v1.6 신규) |
| 20 | `POST /api/v1/orders` | 필요 | JSON (v1.6 신규) |
| 21 | `GET /api/v1/orders/latest` | 필요 | JSON (v1.6 신규) |

## 변경 이력
- 2026-08-15: **v1.6** — 기존 `POST /store/cart` 문서 편입 + order 도메인 3종(`GET /orders/preview`, `POST /orders`, `GET /orders/latest`). POST body 는 `{store}` 만(서버 재계산). 설계 토론 5라운드 합의
- 2026-07-10: **v1.5** — 지역 전환 API(`PUT /users/me/region`, currency 서버 매핑·소급 변환 없음) + store 연동 국가별 세트 분기(KR 4 / US 2, walmart·instacart 편입). UI 대변인 동의
- 2026-07-10: **v1.4** — 식사 완료 API + MealOut 확장(steps/completedAt/timeMinutes/difficulty). UI 대변인 동의
- 2026-07-10: **v1.3** — store 연동 상태 2종 (설정 페이지, 자격증명 미수집 1단계). UI 대변인 동의
- 2026-07-09: **v1.2** — household 도메인(PUT/GET /households/me) + PUT /budget/plans(locked·cuisines 확장). 온보딩 3스텝(프로토타입 1:1) 대응. UI 대변인 동의 완료
- 2026-07-09: **v1.1** — mealplan 도메인 정식 편입(구현 기준: camelCase/uuid/allergies·preferences 요청 필드) + `GET /mealplans/latest` 신규. 팀원 미머지 초안(cbd0623)의 상이점은 구현 우선으로 조정. UI 대변인 동의 완료
- 2026-07-09: v1 최초 확정 — 공통 규격(camelCase/에러/금액/페이지네이션) + auth 5종 + budget 1종. UI 대변인 동의 완료
