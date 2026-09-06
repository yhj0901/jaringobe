# API 레퍼런스 (v1)

> **계약서 원본은 `docs/설계/api-spec.md`** (v1.9) — 스펙 변경은 설계 변경 프로세스 경유. 이 문서는 사용 관점 요약이다. 기준 시점: v0.2.0 (2026-09-05).
> 로컬에서 FastAPI 자동 문서: `http://localhost:8000/docs` (Swagger UI). 라우터 집결점 `backend/app/api/v1/router.py`.

## 공통
- Base `/api/v1`, 요청/응답 **camelCase**, 금액 `{"amount": "500000.00", "currency": "KRW"}`(문자열), 시각 ISO-8601 UTC(Z), 날짜 `YYYY-MM-DD`(사용자 로컬 date)
- 인증: httpOnly 쿠키 `jaringobe_access`(30분) / `jaringobe_refresh`(14일, `Path=/api/v1/auth`)
- 에러: `{"detail": {"code": "...", "message": "..."}}` — `code` 를 프론트 i18n 키로 매핑 (`{domain}.error.{code}`, 미정의는 `common.error.fallback`)
- 공통 에러: 401 `AUTH_REQUIRED`·`AUTH_TOKEN_REVOKED` / 403 `FORBIDDEN_ORIGIN`(상태 변경 메서드 Origin 불일치)·`FORBIDDEN`(타인 리소스) / 404 `NOT_FOUND` / 409 `BUDGET_PLAN_REQUIRED` / 422 `VALIDATION_ERROR`(extra 필드 포함) / 429 `RATE_LIMITED`
- **GET 은 값을 바꾸지 않는다** — 유일한 예외는 최초 호출 시 기본값 행의 멱등 lazy 생성(`GET /cycle`, `GET /notifications/settings`)

## 엔드포인트 — auth / users

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /auth/{provider}/authorize?next=&client=web\|app` | - | provider 인가 302. provider: kakao·google (apple → 404). `next` 는 상대경로만. **`client=app`** 이면 콜백이 웹 리다이렉트 대신 원타임 코드 딥링크(`{APP_SCHEME}://auth?code=`)로 복귀 |
| `GET /auth/{provider}/callback?code&state` | - | 성공: 쿠키 세팅 + `302 {next}?login=success` / 실패: `302 /login?error={AUTH_PROVIDER_DENIED\|AUTH_INVALID_STATE\|AUTH_PROVIDER_ERROR}` (app 은 `{APP_SCHEME}://auth?error=`) |
| `GET /auth/app/session?code=&next=` | - | 앱 원타임 코드 → 웹뷰 쿠키 교환 후 `302 {next}?login=success`. 실패는 사유 구분 없이 `302 /login?error=AUTH_INVALID_APP_CODE`. 코드는 60초·단일 사용 |
| `POST /auth/refresh` | refresh 쿠키 | 200 `{}` + 새 쿠키 (회전). 재사용 감지 시 401 AUTH_TOKEN_REVOKED (전 세션 폐기). `users.last_seen_at` 갱신 |
| `POST /auth/logout` | 필요 | 204, refresh 폐기 + 쿠키 삭제 |
| `GET /users/me` | 필요 | `{id, nickname, email(null 가능), profileImageUrl, locale, country, currency, onboardingCompleted, hasBudgetPlan}` |
| `PUT /users/me/region` | 필요 | 국가 전환(KR/US, currency 서버 매핑) → `UserMeResponse` |

`/auth/*` 는 IP 기준 10회/분.

## household / budget

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `PUT /households/me` · `GET /households/me` | 필요 | 가구 구성 upsert/조회(온보딩). 온보딩 완료 처리 시 사이클 설정 행을 lazy 생성한다 |
| `POST /budget/plans` | 필요 | 게스트 예산안 이전/생성. 201 / 409 `BUDGET_PLAN_EXISTS` / 422 |
| `GET /budget/plans` · `PUT /budget/plans` | 필요 | 조회 / upsert(`locked`·`cuisines` 포함). 5회/분 |

## mealplan

> 예산(`budget_plans`) 있어야 함(409 `BUDGET_PLAN_REQUIRED`). LLM 미설정 시 mock(되먹임 힌트 미반영). 5회/분.

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `POST /mealplans` | 필요 | **202 접수** `{id}` → 백그라운드 생성. `GET /mealplans/{id}` 로 폴링 (`status`: `processing → ready \| over_budget \| failed`). `processing` 이 `MEALPLAN_GENERATION_TIMEOUT_MINUTES`(10) 를 넘기면 `failed` 수렴. 완료 시 `mealplan_done` 푸시 |
| `GET /mealplans/latest` · `GET /mealplans/{id}` | 필요 | 최근/특정 식단 `MealPlanResponse`. 403 `FORBIDDEN` / 404 |
| `PUT /mealplans/{planId}/meals/{mealId}/completion` | 필요 | 식사 완료 토글 → 냉장고 자동 차감/복원(`meals.fridge_deducted` 스냅샷) |
| `POST /mealplans/{id}/regenerate` | 필요 | 재생성 `{scope: all\|meal, mealId?, allergies[], preferences[]}` |
| `POST /mealplans/{id}/cart` | 필요 | 식단−재고 → 컬리 장바구니(완료 끼니 미제외, persist 없음). **UI 미사용** — 제품 접점은 `/orders/*` |
| `POST /mealplans/monthly` | 필요(3회/분) | 월 예산→그 달 식단+첫 주 주문 미리보기. **내부/실험용** (제품 정본은 주간 사이클, 회원 UI 미호출) |

- 프롬프트에 냉장고 재고·임박 재료 힌트가 자동 포함된다(모든 생성 경로). 식단 재료 수량은 LLM 이 줄이지 않고 서버가 재고를 뺀다

## store

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /stores/connections` · `PUT /stores/connections/{store}` | 필요 | `user.country` 세트(KR: kurly·coupang·ssg·naver / US: walmart·instacart) 연동 상태 조회/`{connected}` upsert. 타 국가 스토어 404 `STORE_NOT_SUPPORTED`. 자격증명 미수집 |
| `POST /store/cart` | 필요(3회/분) | 재료목록 → 네이버 쇼핑 검색(컬리 필터) → LLM 선택 → `StoreCartResponse`. 프론트는 이 API 로 preview 를 우회하지 않는다(order 서비스가 내부 호출) |

## fridge

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /fridge` | 필요 | 재고 목록(임박순) `[FridgeItemRead]` — `source ∈ manual \| delivery \| mealplan` (`order` 값은 0012 에서 `delivery` 로 통합) |
| `POST /fridge/items` | 필요 | 수동 추가 201 |
| `PATCH /fridge/items/{id}` · `DELETE /fridge/items/{id}` | 필요 | 수량 수정 / 삭제(배송 등록분 보정에 재사용) |
| `POST /fridge/shortfall` · `POST /fridge/deduct` | 필요 | 감산(비파괴) / 식사 완료 차감(임박 FIFO) |
| `GET /fridge/expiring?days=3` | 필요 | 임박 재료(1~30일) |

## order — 자동주문 + 사이클 상태 머신 (api-spec §7 · §10)

> 경로에 `user_id` 없음 — 본인 행만. `{id}` 를 받는 4종은 타인 주문 403 `FORBIDDEN`, 없는 주문 404 `ORDER_NOT_FOUND`. `simulation=true` 고정(실결제 아님).

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /orders/preview` | 필요 | 현재 사이클에 열린 초안(`draft`/`awaiting_user`)이 있으면 **재계산 없이 스냅샷 반환**(리미터 없음). 없으면 즉석 계산(저장 안 함, **3회/분**): 최신 식단 미완료 끼니 재료 합 − 냉장고 재고 → `needed`/`covered` + 네이버(컬리) 추정가. US 는 네이버 미호출·`0.00 USD`. **`?refresh` 파라미터 없음(v1.9 제거, 보내도 무시)**. 식단 없음 404 `MEALPLAN_NOT_FOUND` |
| `GET /orders/latest` | 필요 | `created_at DESC LIMIT 1` `OrderResponse`. 없으면 404 `ORDER_NOT_FOUND`. **`status` 6종·`confirmedAt` nullable** — `confirmed` 단일 가정 금지 |
| `POST /orders` | 필요(5회/분) | 명시 확정. body **`{store}` 만**(라인·가격 전달 시 422). 서버 재계산 → `confirmed`. 같은 사이클 확정 존재 시 409 `ORDER_ALREADY_CONFIRMED`. 미연동 422 `STORE_NOT_CONNECTED`, needed 없음 422 `NOTHING_TO_ORDER`. **냉장고에 즉시 넣지 않는다**(`deliveryEta` 시점) |
| `POST /orders/{id}/approve` | 필요(5회/분) | 초안 1탭 승인. body 선택 `{excludeNames: string[] ≤40, 각 ≤200자}`(이름만 제외, 가격·수량은 서버 값·총액 재계산). `draft`/`awaiting_user` 아니면 409 `ORDER_INVALID_STATE` |
| `POST /orders/{id}/recalculate` | 필요(**3회/분**) | 열린 초안을 이 사이클 식단·재고·시세로 **재계산·갱신 저장** → `OrderResponse`. `draft` 면 `blockedReason` 초기화, `awaiting_user` 는 상태·사유·`autoConfirmAt(null)` 유지(게이트를 대신 통과시키지 않음). 그 외 상태 409. `GET ?refresh=true` 의 대체 |
| `POST /orders/{id}/cancel` | 필요(5회/분) | `confirmed` 취소. `cycleStart + CYCLE_CANCEL_WINDOW_DAYS`(7) 경과 409 `ORDER_CANCEL_WINDOW_CLOSED`. 등록분은 `order_id` 기준 남은 행만 롤백 |
| `POST /orders/{id}/delivery` | 필요(5회/분) | body `{received: boolean}` (**StrictBool** — `"yes"`/`1` 은 422). `true`: 미등록이면 즉시 등록 + `delivered` / `false`: 롤백 + `deliveryEta`=응답시각+1일 + `deliveryConfirmAttempts`++, 3회 → `deliveryState='unknown'`. `confirmed` 아니면 409 |

**`OrderResponse`**: `{id, store, status, frequency(weekly|biweekly), nextSuggestedAt, estimatedTotal(Money), confirmedAt(null 가능), simulation, items[{name, quantity, unit, lineType(needed|covered), matched, title, unitPrice}], cycleStart, deliveryEta, inboundAt, deliveryState(pending|delivered|unknown), deliveryConfirmAttempts, autoConfirmed, autoConfirmAt, blockedReason}`
**`OrderPreviewResponse`**: `{mealPlanId, storeConnected, country, needed[], covered[], cart, estimatedTotal, notes[], orderId, status(draft|awaiting_user|null), autoConfirmAt, blockedReason, cycleStart}` — `notes` 는 사유 코드(예: `PRICE_LOOKUP_UNAVAILABLE`)

**상태 머신** (`order.service._ALLOWED_TRANSITIONS`): `draft → awaiting_user|confirmed|cancelled|expired|failed` / `awaiting_user → confirmed|cancelled|expired|failed` / `confirmed → cancelled|failed` / `cancelled|expired → failed` / `failed → ∅`. `failed` 는 **예약 상태**(v1.9 까지 생산 경로 없음, 터미널). `blockedReason`: `BUDGET_EXCEEDED` · `UNMATCHED_RATIO` · `STORE_DISCONNECTED` · `AUTO_CONFIRM_OFF` · `US_NO_PRICE` · `MEALPLAN_OVER_BUDGET`.

**액션 리미터 주의(BUG-007, Low 미처리)**: `approve`·`cancel`·`delivery` 와 `PUT /cycle/settings`·`POST /cycle/skip` 가 **하나의 5회/분 버킷을 공유**한다(스펙은 엔드포인트별). 설정을 여러 번 바꾼 직후 승인이 429 가 날 수 있다.

## cycle — 주간 자동 사이클 (api-spec §9)

> 세 엔드포인트가 모두 같은 `CycleState` 를 반환한다. 설정 행이 없으면 최초 호출 시 기본값으로 lazy 생성(404 `CYCLE_NOT_FOUND` 는 없다). 예산안이 없어도 409 를 내지 않고 `weeklyLimit: null`.

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `GET /cycle` | 필요 | 내 사이클 상태. 리미터 없음 |
| `PUT /cycle/settings` | 필요(5회/분) | 부분 갱신 `{enabled?, frequency?(weekly\|biweekly), anchorWeekday?(0=일~6=토), timezone?(IANA), autoConfirm?}`, `extra='forbid'`. `frequency`/`anchorWeekday`/`timezone` 변경 시 `nextRunAt` 즉시 재계산. `autoConfirm=false` 면 열린 초안의 `autoConfirmAt` 을 NULL 로, 다시 true 면 재설정(지난 시각이면 now+1h) |
| `POST /cycle/skip` | 필요(5회/분) | 이번 사이클 1회 건너뛰기(body 없음, 대상은 항상 현재 `cycleStart`). 열린 초안 `cancelled`. 확정 주문 있으면 409 `CYCLE_ALREADY_CONFIRMED`. 멱등 |

**`CycleState`**: `{enabled, frequency, anchorWeekday, timezone, autoConfirm, cycleStart, cycleDays, stage, nextRunAt, skippedCycleStart, weeklyLimit(Money|null), mealPlan{id, status, mealCount, completedMealCount}|null, draftOrder{id, status, estimatedTotal, autoConfirmAt, blockedReason, deliveryEta}|null, currentOrder{id, status, deliveryState, deliveryEta, inboundAt, autoConfirmed}|null, simulation(항상 true)}`

`stage` 13종 (서버 파생값 — 프론트는 이 값 하나로 분기, 클라이언트 추론 금지): `idle` · `generating` · `generated` · `generate_failed` · `drafted` · `awaiting_user` · `confirmed` · `delivered` · `nothing_to_order` · `skipped_user` · `skipped_dormant` · `deferred_quota`(실패 아님, 익일 이월) · `paused`(`enabled=false`)

- `draftOrder` 는 `draft`/`awaiting_user` 에서만, `currentOrder` 는 이번 사이클 최신 주문(상태 무관, 추가 쿼리 0) — `confirmed` 카드의 도착 예정은 `currentOrder.deliveryEta`, `delivered` 카드의 진행은 `mealPlan.completedMealCount/mealCount`
- 품목 단위 배송 진척(N/M)은 제공하지 않는다 — 배송 확인이 주문 단위 CAS 라 데이터가 없다

## notification — 푸시·리마인더 (앱 웹뷰)

| 메서드·경로 | 인증 | 요약 |
|-------------|------|------|
| `PUT /notifications/devices` | 필요(10회/분) | Expo 토큰 upsert `{token(≤4096), platform(ios\|android), locale(ko\|en), timezone(IANA), appVersion?}` → `{id}`. 앱 실행마다 호출(token 기준 idempotent) |
| `DELETE /notifications/devices/{token}` | 필요 | 로그아웃/알림 해제 시 토큰 삭제. 없는 토큰도 204 |
| `GET /notifications/settings` | 필요 | `{settings[{type, enabled, localTime("HH:MM"\|null), timezone\|null}]}` — 행 없으면 기본값 lazy 생성 |
| `PUT /notifications/settings` | 필요(10회/분) | `{settings[1~8]{type, enabled?, localTime?, timezone?}}` 부분 갱신 |

`type` 8종: 리마인더 `meal_reminder_breakfast`(08:00) · `meal_reminder_lunch`(12:00) · `meal_reminder_dinner`(18:30) — `localTime`/`timezone` 설정 대상 / 이벤트 `mealplan_done`(기본 on) · `weekly_nudge`(기본 **off**, P2) · **`order_approval` · `fridge_inbound` · `cycle_paused`**(v1.8 추가, 기본 on, 시각 설정 없음). 푸시 본문 템플릿의 원본은 백엔드 `notification/sender.py::TEMPLATES`(ko/en), `data.path` 는 `/orders`·`/fridge`·`/mealplan/{id}` 만.

## 신규 에러 코드 (v1.8~)
| HTTP | code | 의미 |
|------|------|------|
| 409 | `ORDER_INVALID_STATE` | 허용되지 않는 상태 전이 |
| 409 | `ORDER_ALREADY_CONFIRMED` | 이 사이클에 확정 주문이 이미 있음 |
| 409 | `ORDER_CANCEL_WINDOW_CLOSED` | 취소 허용 기간 경과 |
| 409 | `CYCLE_ALREADY_CONFIRMED` | 확정된 사이클은 건너뛸 수 없음 |
| 422 | `STORE_NOT_CONNECTED` · `NOTHING_TO_ORDER` | 확정/승인 전제 위반 |
| 404 | `ORDER_NOT_FOUND` · `MEALPLAN_NOT_FOUND` | |
| 302 | `AUTH_INVALID_APP_CODE` | 앱 코드 교환 실패 (리다이렉트 query) |

## 프론트 사용 패턴
- 로그인 시작: `location.href = /api/v1/auth/kakao/authorize?next=/` (앱 웹뷰는 `client=app` 을 붙임). 401 수신 시 `POST /auth/refresh` 1회 재시도 → 실패 시 `/login` (`shared/api/client.ts`)
- 회원 홈 마운트: `GET /users/me` → `GET /cycle`(카드) + `GET /stores/connections` + `GET /orders/preview`(저장 초안이면 무비용). `stage='generating'` 일 때만 `GET /mealplans/{id}` 폴링, 그 외 `/cycle` 자동 폴링 없음
- `/orders`: `GET /orders/latest` 의 `OrderResponse` 로 6상태 분기. `latest.cycleStart === preview.cycleStart` 일 때만 이번 사이클 확정 UI. 재계산은 `recalculateOrder(id)`(POST), 응답으로 `latest` 교체
- 파생 상태를 프론트에서 만들지 않는다 — `stage`·`blockedReason` 은 서버 값 그대로

## 선순환 흐름 (실제 호출 순서)
```
로그인(auth) → 온보딩(households/me · budget/plans) → 첫 식단은 홈 CTA(POST /mealplans 202 → 폴링)
  → [스케줄러] D-5 자동 식단 생성(활성 사용자) → D-2 초안(orders draft) + order_approval 푸시
  → 사용자 승인(POST /orders/{id}/approve) 또는 D-1 그레이스 자동확정(5중 게이트)
  → delivery_eta 시점 냉장고 자동 등록(source=delivery) + fridge_inbound 푸시 → 보정(POST /orders/{id}/delivery)
  → 식사 완료(PUT …/completion) 자동 차감 → 다음 D-5 프롬프트에 잔여·임박 재료 되먹임 → 다음 초안에서 재고만큼 감산
```
