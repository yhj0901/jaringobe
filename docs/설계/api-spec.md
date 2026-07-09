# API 스펙 — 예산 락 + AI 식단 자동 생성

> 이 문서는 프론트↔백엔드 **계약서**. 변경은 설계 에이전트 재소집 + 오케스트레이터 승인 후 버전업.

## 공통 규격

- **Base**: `/api/v1`, REST, 리소스 복수형
- **인증**: `Authorization: Bearer <access_token>` (JWT, auth 도메인). 아래 모든 엔드포인트 인증 필수
- **표기**: JSON 필드 **snake_case 통일**
- **금액 표현**: `{ "amount": "500000.00", "currency": "KRW" }` — amount는 **문자열(Decimal 보존)**, currency는 ISO 4217(`KRW`|`USD`). float 금지
- **시각**: ISO-8601 UTC (`2026-07-09T05:00:00Z`)
- **에러 공통 구조**:
  ```json
  { "detail": { "code": "OVER_BUDGET", "message": "..." } }
  ```
  `code`는 프론트 i18n 키로 사용(문구는 프론트 담당). `message`는 디버그용 영어.
- **페이지네이션**(목록): `?page=1&size=20&sort=-created_at`

## 에러 코드
| code | HTTP | 의미 |
|------|------|------|
| `VALIDATION_ERROR` | 422 | 입력 검증 실패 |
| `UNAUTHORIZED` | 401 | 토큰 없음/만료 |
| `FORBIDDEN` | 403 | 소유권 없음(타 가구 리소스) |
| `HOUSEHOLD_REQUIRED` | 409 | 가구 미설정 |
| `BUDGET_NOT_SET` | 409 | 예산 미설정 |
| `LLM_UNAVAILABLE` | 503 | LLM 호출 실패(재시도 초과) |
| `RATE_LIMITED` | 429 | 재생성 한도 초과 |
| `NOT_FOUND` | 404 | 리소스 없음 |

---

## 1. 예산

### POST `/api/v1/budgets` — 예산 설정/락
요청:
```json
{
  "amount": "500000.00",
  "currency": "KRW",
  "period_start": "2026-07-01T00:00:00Z",
  "period_end": "2026-07-31T23:59:59Z",
  "locked": true
}
```
응답 `201`:
```json
{
  "id": 12,
  "household_id": 3,
  "amount": "500000.00",
  "currency": "KRW",
  "period_start": "2026-07-01T00:00:00Z",
  "period_end": "2026-07-31T23:59:59Z",
  "locked": true,
  "created_at": "2026-07-09T05:00:00Z"
}
```
검증: `amount > 0`, `currency ∈ {KRW,USD}`, `period_end > period_start`.

### GET `/api/v1/budgets/current` — 현재 예산
응답 `200`: 위 budget 객체 / 없으면 `409 BUDGET_NOT_SET`.

---

## 2. 식단

### POST `/api/v1/mealplans` — 식단 생성(동기)
요청:
```json
{
  "days": 7,
  "meals_per_day": 3,
  "diet_direction": "balanced"
}
```
- `days` 1~31, `meals_per_day` 1~5, `diet_direction ∈ {balanced,diet,hearty,kids}`(선택)
- 예산·가구·알레르기·선호·region은 서버가 현재 budget/household에서 조회(요청에 넣지 않음)

응답 `201` (또는 초과 시에도 `201` + status):
```json
{
  "id": 45,
  "status": "ready",
  "region": "KR",
  "currency": "KRW",
  "period_start": "2026-07-01T00:00:00Z",
  "period_end": "2026-07-07T23:59:59Z",
  "budget_summary": {
    "budget": { "amount": "500000.00", "currency": "KRW" },
    "planned_cost": { "amount": "408223.00", "currency": "KRW" },
    "remaining": { "amount": "91777.00", "currency": "KRW" },
    "within_budget": true
  },
  "meals": [
    {
      "id": 901,
      "plan_date": "2026-07-01",
      "meal_type": "breakfast",
      "recipe_name": "계란볶음밥",
      "ingredients": [
        { "id": 5001, "name": "계란", "quantity": "4", "unit": "ea",
          "est_cost": { "amount": "2000.00", "currency": "KRW" } }
      ]
    }
  ],
  "notes": []
}
```
- `status ∈ {ready, over_budget}`. `over_budget` 시 `within_budget=false` + `notes`에 초과 안내(자르지 않음).
- 실패: `503 LLM_UNAVAILABLE`, 가구/예산 미설정 시 `409`.

### GET `/api/v1/mealplans/{id}` — 식단 조회
응답 `200`: 위 mealplan 객체. 타 가구 소유 시 `403 FORBIDDEN`, 없으면 `404`.

### POST `/api/v1/mealplans/{id}/regenerate` — 재생성
요청:
```json
{ "scope": "meal", "meal_id": 901 }
```
- `scope ∈ {all, meal}`. `meal`이면 `meal_id` 필수.
- **rate limit**: 가구당 분당 N회(초과 `429 RATE_LIMITED`).
응답 `200`: 갱신된 mealplan 객체(위와 동일 구조).

---

## Pydantic 스키마 규칙
- 요청 `~Create`/`~Regenerate`, 응답 `~Read` 분리
- 금액은 `Money{amount: Decimal(str 직렬화), currency: Literal["KRW","USD"]}` 공용 모델
- 입력 검증은 스키마에서 처리(수동 파싱 금지)

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 합의, UI 대변인 동의)
