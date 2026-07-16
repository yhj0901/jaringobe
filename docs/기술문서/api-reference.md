# API 레퍼런스 (v1)

> **계약서 원본은 `docs/설계/api-spec.md`** — 스펙 변경은 설계 변경 프로세스 경유. 이 문서는 사용 관점 요약이다.
> 로컬에서 FastAPI 자동 문서: `http://localhost:8000/docs` (Swagger UI)

## 공통
- Base `/api/v1`, 요청/응답 **camelCase**, 금액 `{"amount": "500000.00", "currency": "KRW"}`(문자열), 시각 ISO-8601 UTC(Z)
- 인증: httpOnly 쿠키 `jaringobe_access`(30분) / `jaringobe_refresh`(14일, `Path=/api/v1/auth`)
- 에러: `{"detail": {"code": "...", "message": "..."}}` — `code` 를 프론트 i18n 키로 매핑 (`auth.error.{code}`)
- 공통 에러: 401 `AUTH_REQUIRED`·`AUTH_TOKEN_REVOKED` / 403 `FORBIDDEN_ORIGIN` / 422 `VALIDATION_ERROR` / 429 `RATE_LIMITED`

## 엔드포인트

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /auth/{provider}/authorize?next=` | - | provider 인가 302. provider: kakao·google (apple → 404). `next` 는 상대경로만 |
| `GET /auth/{provider}/callback?code&state` | - | 성공: 쿠키 세팅 + `302 {next}?login=success` (동일 이메일 시 `&notice=AUTH_EMAIL_CONFLICT_NOTICE`) / 실패: `302 /login?error={AUTH_PROVIDER_DENIED\|AUTH_INVALID_STATE\|AUTH_PROVIDER_ERROR}` |
| `POST /auth/refresh` | refresh 쿠키 | 200 `{}` + 새 쿠키 (회전). 재사용 감지 시 401 AUTH_TOKEN_REVOKED (전 세션 폐기됨) |
| `POST /auth/logout` | 필요 | 204, refresh 폐기 + 쿠키 삭제 |
| `GET /users/me` | 필요 | `{id, nickname, email(null 가능), profileImageUrl, locale, country, currency, onboardingCompleted, hasBudgetPlan}` |
| `POST /budget/plans` | 필요 | 게스트 예산안 이전/생성. 201 / 409 `BUDGET_PLAN_EXISTS` / 422. 검증: householdSize 1~10, KRW 5만~500만·USD 50~5000, mealDirection ∈ health·diet·hearty·kids |

## 프론트 사용 패턴
- 로그인 시작: `location.href = /api/v1/auth/kakao/authorize?next=/` (rewrites 로 동일 오리진)
- 로그인 복귀 분기: `GET /users/me` → `hasBudgetPlan` + 로컬 게스트 플랜 유무 → `importGuestPlan()` (201→로컬 삭제·온보딩 스킵 / 409→로컬 삭제 / 422→폐기 후 온보딩)
- 401 수신 시: `POST /auth/refresh` 1회 재시도 → 실패 시 `/login` 이동 (`shared/api/client.ts`)

---

## 식단 (mealplan)

> 예산(`budget_plans`) 있어야 함. 없으면 409 `BUDGET_PLAN_REQUIRED`. 비용은 기준가 추정 + 예산 검산(초과 시 `over_budget` 노출, 자르지 않음). LLM 미설정 시 mock.

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `POST /mealplans` | 필요 | 식단 생성. body `{days 1~31, mealsPerDay 1~5, allergies[], preferences[]}` → 201 `MealPlanResponse` |
| `GET /mealplans/{id}` | 필요 | 식단 조회. 403 `FORBIDDEN`(타인) / 404 `NOT_FOUND` |
| `GET /mealplans/latest` | 필요 | 가장 최근 식단(`MealPlanResponse`) |
| `POST /mealplans/{id}/regenerate` | 필요 | 재생성. body `{scope: all\|meal, mealId?, allergies[], preferences[]}` |
| `POST /mealplans/{id}/cart` | 필요 | **원스톱**: 식단−냉장고재고 → 컬리 장바구니. body `{mall, maxPages}` → `MealPlanCartResponse{mealPlanId, needed[], cart}` |
| `POST /mealplans/monthly` | 필요 | **월 예산→그 달 식단+첫 주 주문**. body `{cycle: weekly\|biweekly, mealsPerDay, asOf?, mall, maxPages}` → 201 `MonthlyPlanResponse` |

- `MealPlanResponse`: `{id, status(ready\|over_budget), region, currency, periodStart, periodEnd, budgetSummary{budget, plannedCost, remaining(Money), withinBudget}, meals[{id, planDate, mealType, recipeName, ingredients[{id, name, quantity, unit, estCost(Money|null)}]}], notes[]}`
- `MonthlyPlanResponse`: `{mealPlanId, status, periodStart, periodEnd, days, monthlyBudget, proratedBudget, prorateRatio("22/31"), plannedCost, withinBudget, firstOrder{periodStart, periodEnd, days, needed[ShortfallLine], cart}}`
  - **프로레이션**: 유효예산 = 월예산 × (오늘 포함 남은일수 / 그달 총일수). 식단은 남은 일수, 주문은 첫 주기(weekly=7·biweekly=14일)만 계산.

## 마트 장바구니 (store)

> 네이버 쇼핑 검색(일반검색만) → client-side 필터. 순차 페이지네이션(병렬=429). 키(`NAVER_CLIENT_ID/SECRET`) 없으면 결과 없음.

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `POST /store/cart` | 필요(3회/분) | 재료목록 → 컬리 장바구니. body `{items[{name, quantity?, unit?}], mall: kurly\|all, maxPages 1~10}` → `StoreCartResponse` |

- 파이프라인: `query` 순차조회(최대 1000) → `category1=="식품"` + `mallName` 컬리 필터 → 후보 전량 LLM 선택(키 없으면 최저가) → 장바구니
- `StoreCartResponse`: `{items[{ingredient, matched, title, price(Money|null), mallName, link, candidateCount}], total(Money), matchedCount, notes[]}`

## 가상 냉장고 (fridge)

> user 기준 재고. 금액 없음(수량만). 유통기한 임박순 정렬.

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /fridge` | 필요 | 재고 목록(임박순) → `[FridgeItemRead]` |
| `POST /fridge/items` | 필요 | 재료 추가(배송 자동등록 겸용). body `{items[{name, quantity, unit, expiresAt?, source}]}` → 201 |
| `PATCH /fridge/items/{id}` | 필요 | 수량 수정. body `{quantity}` → `FridgeItemRead` / 403·404 |
| `DELETE /fridge/items/{id}` | 필요 | 삭제 → 204 / 403·404 |
| `POST /fridge/shortfall` | 필요 | **장보기 감산(비파괴)**: 식단−재고. body `{items[{name, quantity, unit}]}` → `{items[ShortfallLine]}` |
| `POST /fridge/deduct` | 필요 | **식사 완료 차감**(임박 FIFO, 0되면 삭제). body `{items[{name, quantity, unit}]}` → `{items[DeductLine]}` |
| `GET /fridge/expiring?days=3` | 필요 | 유통기한 임박(1~30일) → `[FridgeItemRead]` |

- `FridgeItemRead`: `{id, name, quantity, unit, expiresAt(null 가능), source, createdAt}`
- `ShortfallLine`: `{name, unit, needed, fromFridge, toBuy}` — `toBuy` 가 실제 장볼 양
- `DeductLine`: `{name, unit, requested, deducted}` — 재고 부족 시 `deducted < requested`

## 공통 에러 (추가)
- 404 `NOT_FOUND` / 403 `FORBIDDEN` / 409 `BUDGET_PLAN_REQUIRED` / 429 `RATE_LIMITED`(mealplan·store·cart)

## 선순환 흐름 (권장 호출 순서)
```
로그인(auth) → 예산(budget/plans) → 월식단+첫주문(mealplans/monthly)
  → 배송 시 fridge/items 등록 → 식사완료 시 fridge/deduct 차감
  → 다음 주기: (스케줄러 미구현) mealplans/{id}/cart 또는 store/cart 재호출
```

---

## v1.5.1 증분 — notification 도메인 + mealplan 비동기 + 앱 로그인 (2026-07-16)

> 원본 계약: `docs/설계/api-spec.md` v1.5.1 (§1-1 client 파라미터, §1-6, §3-2~3-6, §6-A). 여기는 요약만.

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `PUT /api/v1/notifications/devices` | 필요 | Expo 토큰 등록/갱신 (token upsert, 타 유저 소유 이전) — 앱 실행 시마다 호출 |
| `DELETE /api/v1/notifications/devices/{token}` | 필요 | 로그아웃 시 해제 (idempotent 204) |
| `GET /api/v1/notifications/settings` | 필요 | 5종 lazy 생성 조회 (리마인더 3종 08:00/12:00/18:30 기본) |
| `PUT /api/v1/notifications/settings` | 필요 | 부분 갱신 — next_send_at(UTC) 서버 재계산 |
| `GET /api/v1/auth/app/session?code=&next=` | 불필요 | 원타임 코드 → 웹뷰 쿠키 교환 (302). 앱 전용 |
| `POST /api/v1/mealplans` · `/{id}/regenerate` | 필요 | **202 비동기** — `GET /mealplans/{id}` 폴링. 409 `MEALPLAN_GENERATING` / `MEALPLAN_REGENERATE_EMPTY`(신규 POST 전환) |

- status 4종: `processing → ready|over_budget|failed` (processing 10분 초과 시 서버가 failed 수렴)
- 푸시 페이로드: `{ title, body, data: { v: 1, path: "/mealplan/{id}" } }` — path 는 내부 상대경로만
