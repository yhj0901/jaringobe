# 보안 설계 — 예산 락 + AI 식단 자동 생성

> 글로벌 전제: 국내 개인정보보호법 + GDPR/CCPA. 시크릿은 `.env` + `core/config.py` 경유만.

## 1. 인증 (Authentication)
- **JWT (Access + Refresh)** — 발급/검증은 `auth` 도메인 담당. 본 기능은 Access 토큰 검증 의존성(`deps`)만 사용.
- 모든 엔드포인트 인증 필수. 만료/무효 토큰 → `401 UNAUTHORIZED`.

## 2. 인가 (Authorization)
- 모든 리소스(budget/meal_plan)는 **요청자의 household 소유 여부 검증**. 타 가구 리소스 접근 → `403 FORBIDDEN`.
- URL의 `{id}`로 직접 조회 후 `household_id == 현재 사용자 household` 확인 (경로 파라미터 신뢰 금지).
- **CWE-639 (IDOR)**, **CWE-284 (Improper Access Control)** 방어.

## 3. 입력 검증
- 모든 입력 Pydantic 스키마 검증(수동 파싱 금지): 예산 `amount>0`, `currency` 화이트리스트, `period_end>period_start`, `days/meals_per_day` 범위, `diet_direction` enum.
- **CWE-20 (Improper Input Validation)**.

## 4. LLM 프롬프트 인젝션 (OWASP LLM01)
- 사용자 자유 텍스트(선호/알레르기)가 프롬프트에 유입 → **시스템 지시와 사용자 데이터 구조적 분리**(역할 구분, 데이터는 명시 필드로 전달).
- LLM 출력은 신뢰 대상 아님: **알레르기 위반은 생성 후 코드로 재검증**(위반 시 재생성/제거). 금액 계산도 LLM에 위임하지 않고 백엔드 산출.

## 5. 개인정보 (알레르기 = 민감정보)
- 알레르기 정보는 **건강 관련 민감정보**(GDPR 특수범주 / 국내 민감정보) → 수집 최소화, **로그 출력 금지**, 접근 최소 권한.
- 저장은 `household` 도메인. 동의 획득 UX는 auth/household 온보딩에서 처리(설계 연계).
- 식단/예산 데이터 보관: 계정 존속 기간, 탈퇴 시 파기.

## 6. 자원 남용 / 비용 방어
- 식단 **재생성 rate limit**(가구당 분당 N회) → `429 RATE_LIMITED`. LLM 비용/DoS 방어.
- LLM 호출 **타임아웃(25s) + 재시도 상한(N)** — 무한 루프/행 방지.
- **CWE-770 (Allocation of Resources Without Limits)**.

## 7. 전송/네트워크
- CORS: 개발 전체 허용, **배포 시 프론트 도메인 화이트리스트**로 제한.
- 배포: 8000 직접 노출 대신 **Nginx(443) + HTTPS** 뒤로(후속 인프라). postgres 5432 외부 노출 금지.

## 8. 데이터 접근 / 시크릿
- 모든 DB 접근 SQLAlchemy 표현식(파라미터 바인딩) — raw SQL 하드코딩 금지. **CWE-89 (SQLi)** 방어.
- `ANTHROPIC_API_KEY` 등 시크릿은 `.env` 전용, 코드/로그/status JSON 기록 금지. **CWE-312/522** 방어.

## CWE 요약
| CWE | 항목 | 대응 |
|-----|------|------|
| CWE-639 | IDOR | household 소유권 검증 |
| CWE-284 | 부적절한 접근제어 | 인증 의존성 필수 |
| CWE-20 | 입력 검증 미흡 | Pydantic 스키마 |
| CWE-770 | 자원 제한 없음 | 재생성 rate limit, LLM 타임아웃/재시도 상한 |
| CWE-89 | SQL 인젝션 | SQLAlchemy 표현식 |
| CWE-312/522 | 민감정보/자격증명 평문 | .env, 알레르기 로그 금지 |
| OWASP LLM01 | 프롬프트 인젝션 | 데이터/지시 분리 + 출력 코드 재검증 |

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 합의)
