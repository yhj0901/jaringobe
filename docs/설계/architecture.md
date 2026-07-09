# 아키텍처 설계 — 예산 락 + AI 식단 자동 생성

> 대상 기획: `docs/기획/예산락-AI식단-자동생성.md` · 제품 기준: `docs/사업/사업계획서-요약.md`

## 1. 전체 구조

```
[Next.js (App Router)]
   │  REST / JSON, Authorization: Bearer <JWT>
   ▼
[FastAPI  /api/v1]
   ├─ budget    라우터 → 서비스
   └─ mealplan  라우터 → 서비스
                  │
        ┌─────────┼──────────────┬───────────────┐
   LLMProvider   PriceProvider   BudgetChecker    (household 조회)
   (Claude API)  (v1: DB 기준가) (예산 검산·재시도)
                  │
             [PostgreSQL 16]  (async / asyncpg)
```

- **도메인 격리**: `budget`, `mealplan` 라우터/서비스/모델/스키마를 도메인별로 분리. `auth`(JWT)·`household`(가구·알레르기·선호)에 의존(조회만).
- **외부 의존 격리**: LLM 호출과 재료 가격 조회는 각각 `LLMProvider`, `PriceProvider` 인터페이스 뒤로 숨긴다 → v1 구현을 후속 `store` 어댑터/실모델로 교체 가능.

## 2. 식단 생성 흐름 (핵심 시퀀스)

```
POST /api/v1/mealplans
  1. JWT 인증 → household 소유권 확인
  2. 입력 검증 (예산·기간·통화)   [Pydantic]
  3. household 조회 (구성원/알레르기/선호/region)
  4. LLMProvider.generate_meals(입력)         → 식단(끼니·재료) 초안
  5. 알레르기 하드 검증 (코드)                 → 위반 시 재생성 요청
  6. PriceProvider.price(재료, region)        → 기준가
  7. BudgetChecker: 총비용 산출 → 예산 비교
       ├─ 이내      → status=ready
       └─ 초과      → LLMProvider 재요청(최대 N회, "X 초과, 저렴하게")
                        ↳ N회 후에도 초과 → status=over_budget (투명 노출, 자르지 않음)
  8. meal_plan/meal/meal_ingredient 저장 (트랜잭션)
  9. 응답 (식단 + budget_summary + status)
```

- **동기 처리(v1)**: 요청-응답 내 완결. 타임아웃 **25s**, LLM 호출 실패 시 재시도(지수 백오프, 최대 N회).
- **비동기 경로(후속)**: 생성 지연이 커지면 `202 Accepted + jobId` → `GET /mealplans/{id}` 폴링(또는 SSE)으로 승격. 응답 스키마는 동일 유지하도록 설계.

## 3. 예산 방어 (선순환 루프 정합성)

- 프로토타입에서 검증된 **"LLM 편성 → 백엔드 검산 → 재시도 → 초과 시 투명 노출"** 을 그대로 채택.
- 비용 산출은 **백엔드(결정적)** 가 `ingredient_price_ref` 로 수행 — LLM에 금액 계산을 맡기지 않는다(정합성).
- v1은 냉장고 재고 0 가정. 후속 `fridge` 연계 시 `식단 − 재고 = 필요분` 감산이 6번 단계 앞에 삽입됨(루프의 ③④ 단계 연결점).

## 4. 오류/폴백 전략

| 상황 | 처리 |
|------|------|
| LLM 타임아웃/오류 | 재시도(최대 N) → 실패 시 `503 LLM_UNAVAILABLE` |
| 예산 N회 초과 | `status=over_budget` + budget_summary 로 초과액 노출 (에러 아님) |
| 가격 미존재 재료 | region 기준가 없으면 기본 추정 규칙 적용 + `key_findings`에 표시 |
| household 미설정 | `409 HOUSEHOLD_REQUIRED` |

## 5. 관련 설계 문서
- API 계약: [api-spec.md](api-spec.md)
- DB: [db-schema.md](db-schema.md)
- 보안: [security-design.md](security-design.md)
- store 어댑터(후속), ui-design(프론트 담당)은 v1 범위 외 — 인터페이스 지점만 본 문서에 명시.
