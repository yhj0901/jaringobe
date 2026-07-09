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
