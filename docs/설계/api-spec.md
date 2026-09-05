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
| `429 RATE_LIMITED` | **3회/분** — 기존 store 리미터와 동일 스펙 재사용 (네이버+LLM 비용 방어, CWE-770). **(v1.9 명시)** 저장 초안 스냅샷을 그대로 돌려주는 호출(외부 조회 없음)에는 적용하지 않는다 — 10-5 |

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
  "mealPlan":   { "id": "uuid", "status": "ready", "mealCount": 21, "completedMealCount": 0 },
  "draftOrder": {
    "id": "uuid",
    "status": "draft",
    "estimatedTotal": { "amount": "58200.00", "currency": "KRW" },
    "autoConfirmAt": "2026-09-05T00:00:00Z",
    "blockedReason": null,
    "deliveryEta": null
  },
  "currentOrder": {
    "id": "uuid",
    "status": "draft",
    "deliveryState": "pending",
    "deliveryEta": null,
    "inboundAt": null,
    "autoConfirmed": false
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
| `mealPlan` | object\|null | 이번 사이클의 최신 식단 요약. 없으면 null. **(v1.9)** `mealCount`·`completedMealCount` 추가 — 아래 "진행 수치" 참조 |
| `draftOrder` | object\|null | `draft`/`awaiting_user` 주문 요약. 없으면 null. **확정 이후(`confirmed`/`delivered`)에는 항상 null** — 배송 정보는 `currentOrder` 에서 읽는다 (v1.9 명시) |
| `currentOrder` | object\|null | **(v1.9 신규)** 이번 사이클(`cycleStart`)의 최신 주문 요약 — **상태 무관**. 주문 행이 없으면 null. 아래 "진행 수치" 참조 |
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

#### 진행 수치 (v1.9 신규) — `currentOrder` · `mealPlan.mealCount` / `mealPlan.completedMealCount`

배경: ui-design 14-2 의 `confirmed` 카드("{deliveryEta} 도착 예정")와 `delivered` 카드("{완료}/{전체} 완료")가 요구하는 값이 v1.8 `CycleState` 에 없었다. `draftOrder` 는 `draft`/`awaiting_user` 에서만 채워지므로 확정 이후에는 배송 정보를 읽을 곳이 없고, 끼니 완료 수치도 없어 프론트가 일반 진행 문구로 우회했다(2026-09-04 구현 워커 합의). 아래는 **백엔드가 이미 가진 데이터**로만 채운다.

**`currentOrder`** — `cycle.service.build_cycle_state` 가 이미 조회하는 "이번 사이클 최신 주문 1행"(`_current_order`, `created_at DESC LIMIT 1`, 상태 무관)을 그대로 노출한다. **추가 쿼리 0건.**

| 필드 | 타입 | 출처 |
|------|------|------|
| `id` | uuid | `orders.id` |
| `status` | `draft \| awaiting_user \| confirmed \| cancelled \| expired \| failed` | `orders.status` |
| `deliveryState` | `pending \| delivered \| unknown` | `orders.delivery_state` — 배송 진행의 서버 정본(3값) |
| `deliveryEta` | datetime\|null | `orders.delivery_eta` (UTC). 초안은 null |
| `inboundAt` | datetime\|null | `orders.inbound_at` — 냉장고 등록 완료 시각. null = 미등록 |
| `autoConfirmed` | boolean | `orders.auto_confirmed` |

- 라인·금액은 넣지 않는다 — 스냅샷은 `GET /orders/latest` 가 담당하며 `_current_order` 는 `items` 를 로드하지 않는다(넣으면 추가 쿼리가 생긴다).
- `stage` 파생 규칙은 바뀌지 않는다. `currentOrder` 는 표시용 보조값이며 프론트가 이것으로 단계를 추론하지 않는다(ui-design 14-7). `draftOrder` 는 하위호환을 위해 그대로 둔다(같은 행을 두 번 내리는 중복은 의도된 것 — 기존 프론트 훅을 깨지 않기 위함).

**`mealPlan.mealCount` / `mealPlan.completedMealCount`** — 이번 사이클 식단의 전체 끼니 수와 `completed_at IS NOT NULL` 끼니 수. `delivered` 카드의 "{완료}/{전체} 완료" 가 이 값이다. 집계 1건(`SELECT count(*), count(completed_at) FROM meals WHERE meal_plan_id = :id`) 이 추가되며 `ix_meals_plan_date` 의 선두 컬럼으로 커버된다. `mealPlan` 이 null 이면 집계하지 않는다. 9-1 의 성능 목표(p95 < 300ms) 안에서 감당 가능한 비용이다.

**넣지 않는 것 — 품목 단위 배송 진척("배송 완료 품목 수 / 전체 품목 수")**: 백엔드에 그 데이터가 **없다**. 배송 확인은 **주문 단위** compare-and-set(`orders.inbound_at`, 10-3)이고 `order_items` 에는 라인별 배송·등록 상태 컬럼이 없다. 냉장고 등록도 needed 라인 전체를 한 트랜잭션에 넣는다(architecture 3-9-9). 따라서 "N/M 품목 배송 완료" 는 항상 0/M 또는 M/M 이 되어 수치로서 의미가 없고, 만들려면 `order_items` 라인별 상태 컬럼 + 부분 배송 UX + 스토어 배송 웹훅(v1.8 이관 항목)이 선행돼야 한다. 그 전까지 배송 진행은 `currentOrder.deliveryState`(3값)로, 이번 주 소비 진행은 `mealPlan` 집계로 표시한다.

### 9-1. `GET /api/v1/cycle` — 인증 필요 (v1.8 신규)

내 사이클 상태. 설정 행이 없으면 기본값으로 생성 후 반환. 리미터 없음(읽기).

| HTTP | 내용 |
|------|------|
| `200` | `CycleState` |
| `401 AUTH_REQUIRED` | 공통 |

- 예산안이 없는 사용자(`BUDGET_PLAN_REQUIRED` 대상)는 **409 를 내지 않는다** — `weeklyLimit: null` 로 반환하고 홈이 예산 설정 CTA 를 띄운다. 홈 진입 API 가 409 를 내면 화면이 멈춘다.
- 성능 목표 p95 < 300ms. 내부 조회는 설정 1행 + 최신 식단 1행 + 이번 사이클 최신 주문 1행(상태 무관 — v1.9 `currentOrder` 는 이 행을 재사용, 추가 조회 없음) + 확정 합계 1건 + **(v1.9)** 끼니 집계 1건(`meals` count/completed, `ix_meals_plan_date` 선두 컬럼).

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
| `status` | `confirmed` 만 | `draft` · `awaiting_user` · `confirmed` · `cancelled` · `expired` · `failed` (`failed` 는 **예약 상태 — v1.9 까지 생산 경로 없음**, 10-8) |
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
- ~~강제 재계산: `?refresh=true` — 초안을 최신 계산으로 **갱신 저장**한다.~~ **v1.9 에서 계약 제거.** GET 이 저장 초안을 갱신하는 부작용 경로였고, Origin 검증이 `POST/PUT/PATCH/DELETE` 에만 걸려 CSRF 이중 방어를 우회했다(security-design 5-7). 재계산은 **`POST /orders/{id}/recalculate`(10-7)** 로 옮긴다. 목표 상태: 서버는 `refresh` 를 선언하지 않으며 보내도 무시된다(일반 GET 과 동일 동작). 구현 반영 전까지의 현행 동작은 10-7 "이행" 항목 참조.
- 저장된 초안이 없으면 기존 v1.6 동작(즉석 계산, 저장 안 함) 그대로.
- **리미터 (v1.9 명시 — 2026-09-04 리뷰 P0-2 수정 구현 기준)**: 저장 초안 스냅샷을 돌려주는 호출은 외부 조회가 없으므로 리미터를 **적용하지 않는다**. 즉석 계산(저장 초안 없음)만 **3회/분**(`order_preview_user_limiter`). §7-1 의 "3회/분" 은 이 경우에 한정된다.

### 10-6. `POST /api/v1/orders` — 변경 없음 (명시적 확정, v1.6 유지)

사용자가 사이클과 무관하게 직접 확정하는 경로로 유지한다. 단 서버가 `cycle_start` 를 현재 사이클로 채우므로 **부분 유니크 인덱스의 적용을 받는다**. 이 사이클에 이미 확정 주문이 있으면 `409 ORDER_ALREADY_CONFIRMED`(신규). 확정 즉시 inbound 하던 동작은 **제거**되고 `delivery_eta` 시점으로 옮겨진다.

### 10-7. `POST /api/v1/orders/{id}/recalculate` — 인증 필요 (v1.9 신규)

열린 초안(`draft`/`awaiting_user`)을 **이 사이클 식단(`period_start = cycle_start`)·냉장고 재고·시세로 다시 계산해 갱신 저장**한다. v1.8 의 `GET /orders/preview?refresh=true` 가 하던 일을 **메서드만 바꿔** 옮긴 것이며 계산 로직은 동일하다(`order.service.preview_order(refresh=True)` 의 초안 갱신 분기). body 없음 — 라인·가격·`matched` 를 받지 않는다(CWE-602).

| HTTP | code | 상황 |
|------|------|------|
| `200` | — | `OrderResponse` (갱신된 초안 스냅샷. `status`·`autoConfirmAt` 은 유지) |
| `401` | `AUTH_REQUIRED` | 공통 |
| `403` | `FORBIDDEN` | 타인 주문 |
| `403` | `FORBIDDEN_ORIGIN` | Origin 불일치 (POST 이므로 미들웨어 자동 적용 — 이 경로를 만든 이유) |
| `404` | `ORDER_NOT_FOUND` | |
| `404` | `MEALPLAN_NOT_FOUND` | 이 사이클의 식단이 없음 |
| `409` | `ORDER_INVALID_STATE` | `draft`/`awaiting_user` 가 아님 (`confirmed`·`cancelled`·`expired`·`failed` 는 재계산 대상이 아니다) |
| `429` | `RATE_LIMITED` | **3회/분** — `order_preview_user_limiter` 재사용 (네이버+LLM 비용, CWE-770) |

- 부작용(현 `refresh=true` 구현과 동일): `meal_plan_id`·`estimated_total`·`currency`·`items` 를 재계산값으로 교체. `status='draft'` 이면 `blocked_reason=NULL` 로 초기화. `awaiting_user` 는 상태·`blocked_reason`·`auto_confirm_at`(=NULL) 을 **그대로 둔다** — 차단 해소 판정은 자동확정 게이트(architecture 3-9-5)나 승인(10-1)이 하며, 재계산이 게이트를 대신 통과시키지 않는다.
- 응답을 `OrderResponse` 로 둔 이유: `/orders` 화면은 `GET /orders/latest` 의 `OrderResponse` 로 초안을 그리므로(ui-design 14-3) 재계산 결과를 같은 형으로 받아 `latest` 를 교체하면 된다. `OrderPreviewResponse` 로 돌려주면 프론트가 두 형을 합성해야 한다.
- 경로를 `POST /orders/preview/refresh` 가 아니라 `/{id}/recalculate` 로 둔 이유: 갱신 대상은 **저장된 초안 행**이며, 기존 3종 조작(`approve`/`cancel`/`delivery`)과 같은 `/{id}/{동사}` 규약·소유자 검증(403) 경로를 재사용한다. 저장 초안이 없을 때의 "즉석 계산"은 부작용이 없으므로 GET(10-5)에 남긴다.
- **이행**: 백엔드·프론트가 같은 저장소에 있고 미출시이므로 병행 기간을 두지 않는다. 후속 구현 태스크에서 ① 라우터에 10-7 추가 ② `GET /orders/preview` 의 `refresh` 파라미터 제거 ③ 프론트 `fetchOrderPreview(refresh)` 호출을 `recalculateOrder(id)` 로 교체(`OrdersController.handleRefresh`) 를 **한 PR** 로 반영한다. 반영 전까지 현행 `?refresh=true` 는 security-design 5-7 의 "잠정 수용 조건" 아래 동작한다.

### 10-8. `failed` 상태 — 예약 상태와 복구 경로 결정 (v1.9)

**결정: 전용 복구 엔드포인트를 만들지 않는다. 현행 우회(`GET /orders/preview?refresh=true` = "다시 계산하기")도 정식 계약으로 승격하지 않는다. `failed` 는 v1.9 까지 "생산 경로 없는 예약 상태" 로 명시한다.**

근거 (2026-09-04 코드 대조):
1. **백엔드에 `failed` 를 만드는 경로가 없다.** `orders.status` CHECK(리비전 0011)와 `order.service._ALLOWED_TRANSITIONS`(`* → failed`, `failed → ∅`)에만 등장한다. 초안 생성 실패는 주문 행을 만들지 않고 `user_cycle_settings.last_stage='generate_failed'` 로 남으며(architecture 3-9-3), 확정 중 예외는 롤백되어 상태가 바뀌지 않는다. 즉 사용자는 v1.9 에서 `failed` 주문을 볼 수 없다.
2. **현행 우회는 아무것도 복구하지 않는다.** `preview_order(refresh=True)` 는 `draft`/`awaiting_user` 행만 갱신한다. `failed` 행이 최신 주문이면 즉석 계산 결과만 돌려주고 행은 그대로 남아 `/orders` 는 계속 실패 카드를 보인다. 동작하지 않는 우회를 계약으로 굳히면 문서가 거짓이 된다.
3. **복구 의미는 생산자에 달려 있다.** `failed` 의 실제 생산자는 실결제(기획 Q4, 범위 밖)의 결제 실패다. 그때의 복구가 "결제 재시도"인지 "초안으로 되돌려 재승인"인지는 결제 설계가 정한다. 지금 `POST /orders/{id}/retry` 를 확정하면 존재하지 않는 실패에 대한 추측 계약이 된다.

계약상 확정하는 것:
- `failed` 는 **터미널 상태**다. 재계산(10-7)·승인(10-1)·취소(10-2)·배송 보정(10-3) 모두 `409 ORDER_INVALID_STATE`.
- `failed` 는 부분 유니크 인덱스(`uq_orders_confirmed_cycle`·`uq_orders_open_cycle`) 대상이 아니므로 **같은 사이클의 새 초안·재확정을 막지 않는다**. 시스템 차원의 복구 경로는 `POST /orders`(10-6, 명시 확정)와 다음 사이클 정상 진행이며, 별도 엔드포인트가 필요 없다.
- 프론트는 `failed` 를 `cancelled`/`expired` 와 같은 **터미널 카드**(다음 사이클 안내, 조작 CTA 없음)로 그린다(ui-design 14-3 v1.9). "다시 계산하기" CTA 는 제거한다. 분기 자체는 유지한다(10-4 계약의 6값 방어).
- 실결제 설계에서 `failed` 생산 경로가 생기면 그 설계가 복구 엔드포인트(예: `POST /orders/{id}/retry`)와 `failed → *` 전이를 함께 확정하고 본 절을 개정한다.

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
| 기간 경계 | `periodStart` 포함, `periodEnd` **제외**. `firstOrder`에도 동일하게 적용하며 `days = periodEnd - periodStart`. 2026-09-06부터 기존 포함 종료일을 제외 종료일로 변경해 주간·DB 저장·공통 GET 응답과 통일한다. 예: 9/24부터 7일은 `periodEnd: 2026-10-01`이며 마지막 식사일은 9/30이다 |

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
| `POST /api/v1/orders/{id}/recalculate` | 필요 | JSON (**v1.9 신규** — `preview?refresh=true` 대체, 10-7) |
| `POST /api/v1/mealplans/monthly` | 필요 | JSON (기존 구현, v1.8 문서 편입 — **내부/실험용**) |

**확장(기존 경로)**

| 메서드·경로 | 변경 | 하위호환 |
|-------------|------|----------|
| `GET /api/v1/orders/latest` | status 6종 확장 + 필드 8종 추가 + `confirmedAt` nullable | ⚠ **깨짐** — 10-4 |
| `GET /api/v1/orders/preview` | 초안 스냅샷 반환 + 필드 5종 추가 + ~~`?refresh`~~ (**v1.9 제거** → 10-7) | ✅ 추가만 (v1.9: `refresh` 제거는 프론트 호출 교체와 한 PR) |
| `GET/PUT/POST /api/v1/cycle*` | `CycleState` 에 `currentOrder` + `mealPlan.mealCount/completedMealCount` 추가 (**v1.9**, §9 진행 수치) | ✅ 추가만 |
| `POST /api/v1/orders` | `cycle_start` 부여 → 멱등 제약 적용, 확정 즉시 inbound 제거 | ⚠ 신규 409 |
| `GET/PUT /api/v1/notifications/settings` | type 3종 추가 | ✅ 추가만 |
| `POST /api/v1/mealplans` | 변경 없음 (v1.5 202 승계) | ✅ |

## 변경 이력
- 2026-09-04: **v1.9** — 구현 정합 증분(신규 기능 없음). ① `CycleState` 에 `currentOrder`(추가 쿼리 0) + `mealPlan.mealCount/completedMealCount`(집계 1건) 추가, 품목 단위 배송 수치는 **서버 데이터 부재로 미제공** 사유 명시(§9 진행 수치) ② `failed` 주문 전용 복구 경로 **신설하지 않음** — 생산 경로 없는 예약 상태로 확정, 현행 `refresh` 우회도 승격하지 않음(10-8) ③ `GET /orders/preview?refresh=true` **계약 제거** → `POST /orders/{id}/recalculate` 신설(10-7, 3회/분, 에러 코드 재사용) — GET 부작용·Origin 검증 우회 해소(security-design 5-7) ④ preview 리미터 실제 동작(저장 스냅샷 미적용) 명시(7-1·10-5). 코드 변경 없음 — 구현은 후속 태스크
- 2026-08-15: **v1.6** — 기존 `POST /store/cart` 문서 편입 + order 도메인 3종(`GET /orders/preview`, `POST /orders`, `GET /orders/latest`). POST body 는 `{store}` 만(서버 재계산). 설계 토론 5라운드 합의
- 2026-08-30: **v1.8** — 주간 자동 사이클: cycle 도메인 3종(`GET /cycle`·`PUT /cycle/settings`·`POST /cycle/skip`) + order 3종(`approve`·`cancel`·`delivery`) 신규, `GET /orders/latest` **계약 확장(하위호환 깨짐 — 10-4 사유 기재)**, `GET /orders/preview` 초안 스냅샷(추가만), notification type 3종, `POST /mealplans/monthly` **내부/실험용** 표기. 신규 에러 4종. UI 대변인 동의 완료
- 2026-07-10: **v1.5** — 지역 전환 API(`PUT /users/me/region`, currency 서버 매핑·소급 변환 없음) + store 연동 국가별 세트 분기(KR 4 / US 2, walmart·instacart 편입). UI 대변인 동의
- 2026-07-10: **v1.4** — 식사 완료 API + MealOut 확장(steps/completedAt/timeMinutes/difficulty). UI 대변인 동의
- 2026-07-10: **v1.3** — store 연동 상태 2종 (설정 페이지, 자격증명 미수집 1단계). UI 대변인 동의
- 2026-07-09: **v1.2** — household 도메인(PUT/GET /households/me) + PUT /budget/plans(locked·cuisines 확장). 온보딩 3스텝(프로토타입 1:1) 대응. UI 대변인 동의 완료
- 2026-07-09: **v1.1** — mealplan 도메인 정식 편입(구현 기준: camelCase/uuid/allergies·preferences 요청 필드) + `GET /mealplans/latest` 신규. 팀원 미머지 초안(cbd0623)의 상이점은 구현 우선으로 조정. UI 대변인 동의 완료
- 2026-07-09: v1 최초 확정 — 공통 규격(camelCase/에러/금액/페이지네이션) + auth 5종 + budget 1종. UI 대변인 동의 완료
