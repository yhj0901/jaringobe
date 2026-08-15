# 보안 설계서 — 소셜 로그인/JWT + 게스트 데이터

> 대상: auth 도메인 전체 + 게스트 예산안 이전. 마트 자격증명 암호화는 store 기획 시 본 문서에 증보한다.

## 1. 소셜 로그인 (OAuth Authorization Code, 백엔드 주도)

```
프론트 → GET /auth/{provider}/authorize?next=/
  ① state = 서명 토큰(JWT, exp 10분) { nonce, next, provider }   ← CWE-352
  ② provider 인가 URL 302
provider → GET /auth/{provider}/callback?code&state
  ③ state 서명·만료·provider 일치 검증 (실패: AUTH_INVALID_STATE)
  ④ code → 토큰 교환 (서버↔서버, 시크릿은 .env 전용)              ← CWE-798/522
  ⑤ 프로필 정규화 → auth_identities(provider, provider_user_id) 조회
     - 없음 → users 생성 (신규 세션 — 세션 고정 없음)              ← CWE-384
     - 동일 이메일 타 provider 존재 → 자동 통합 금지, notice 만    ← CWE-287
  ⑥ provider access token 은 프로필 조회 후 즉시 폐기 (저장 금지)
  ⑦ JWT 쿠키 세팅 → next(화이트리스트 검증된 상대경로)로 302        ← CWE-601
```

- `next` 검증 규칙: `/` 로 시작하는 상대 경로만 허용, `//`·`\` ·스킴 포함 시 기본값 `/` 로 대체
- 어댑터 공통 인터페이스: `get_authorize_url(state) / exchange_code(code) / fetch_profile(token) → NormalizedProfile{provider_user_id, nickname?, email?, profile_image_url?}` — 애플(P1)도 동일 인터페이스 (relay 이메일은 email 필드로 수용)

## 2. JWT + 쿠키 정책

| 항목 | 정책 |
|------|------|
| Access (`jaringobe_access`) | JWT HS256, **수명 30분**, claims: `sub(user_id), exp, iat, jti` |
| Refresh (`jaringobe_refresh`) | 불투명 랜덤 256bit — DB 에 **SHA-256 해시만** 저장, 수명 14일 |
| 쿠키 공통 | `HttpOnly; Secure; SameSite=Lax` (localStorage 저장 금지 — XSS 격리) |
| Refresh 쿠키 Path | `Path=/api/v1/auth` — refresh/logout 외 전송 차단 (노출면 최소화) |
| 회전 | refresh 사용 시 기존 revoke + 신규 발급, `rotated_from` 체인 기록 |
| **재사용 감지** | revoked 된 refresh 재사용 시 해당 유저 **전 세션 즉시 폐기** + 401 `AUTH_TOKEN_REVOKED` ← CWE-613 |
| 로그아웃 | refresh 서버측 revoke + 쿠키 삭제. access 는 잔여 수명(≤30분) 자연 만료 허용 (MVP — 블랙리스트는 추후 필요 시) |

## 3. CSRF / CORS / Origin

- 쿠키 인증이므로 CSRF 표면 존재 → **이중 방어**: ① `SameSite=Lax` ② 상태 변경 메서드(POST 등)에 **Origin 헤더 검증 미들웨어** (`FRONTEND_ORIGIN` 불일치 시 403 `FORBIDDEN_ORIGIN`)
- CORS: Next.js rewrites 프록시로 동일 오리진 — **백엔드 CORS 미허용(기본 차단)**. 직접 호출 필요 시 설계 변경 프로세스 경유
- 백엔드는 프록시 뒤 배치 전제 — 직접 노출 시에도 위 Origin 검증이 유지되도록 미들웨어는 앱 레벨에 둔다

## 4. 입력 검증 / Rate Limit

| 대상 | 규칙 |
|------|------|
| `POST /budget/plans` | **서버 전량 재검증** (householdSize 1~10, 통화별 금액 범위, mealDirection 열거, Decimal 소수 2자리) — localStorage 변조 대비 ← CWE-20/602 |
| `provider` path | 열거값 외 404 |
| OAuth 콜백 파라미터 | code/state 형식·길이 상한 검증 |
| Rate limit | `/auth/*` IP 기준 10회/분, `/budget/plans` 유저 기준 5회/분 (초과 429 `RATE_LIMITED`) ← CWE-307 |

## 5. 게스트 데이터 (프론트)

- localStorage 키 `jaringobe.guest.v1`: 예산안(인원·금액·통화·방향) + 프롬프트 노출 이력 + 저장 시각(30일 만료) — **PII·토큰 저장 금지** ← CWE-922
- 게스트 상태 서버 전송 금지 (가입 시 이전 1회 제외). 표시 시 React 기본 이스케이프, `dangerouslySetInnerHTML` 금지 ← CWE-79
- 이전 성공/409 시 즉시 삭제, 422 시 폐기

## 5-1. mealplan 접점 (v1.1 증보)

- **CWE-639**: `/mealplans/{id}`·`/regenerate` 소유자 검증(구현 확인), `latest` 는 user_id 스코프 쿼리로 구조적 차단
- **CWE-770**: 생성/재생성 유저 5회/분(구현 확인) + 프론트 버튼 비활성. latest(읽기)는 미적용
- **CWE-79/117**: `allergies`/`preferences` 항목당 30자·최대 10개 서버 검증, **로그 기록 금지**(건강 관련 민감 입력 — 저장소 없음, 요청 전달만)

## 5-2. household/온보딩 접점 (v1.2)
- CWE-20/602: members 서버 전량 재검증(유형 enum·유형별 나이 범위·1~10명), cuisines enum·개수(≤6), locked boolean
- CWE-639: /households/me·PUT /budget/plans 는 인증 유저 본인 스코프만
- 최소 수집: 구성원은 유형+나이만(이름·실성별 정보 없음). visited 마커는 비식별 boolean 성격

## 5-3. 설정/스토어 연동 접점 (v1.3)
- CWE-639 본인 스코프(connections) / CWE-20 store·status enum 검증 / **자격증명 미수집**(1단계) — 실연동 시 암호화 저장 설계 필수(store 본설계)

## 5-4. 지역 전환 / 국가별 스토어 접점 (v1.5)
- **CWE-20**: `PUT /users/me/region` 의 `country` 열거(KR/US) 검증. **currency 는 클라이언트 입력 불신 — 서버가 country 로부터 매핑**(통화·국가 불일치 상태를 원천 차단). store enum 검증은 `user.country` 허용 세트 기준(국가 밖 스토어 PUT → 404 `STORE_NOT_SUPPORTED`)
- **CWE-639**: region·connections 모두 경로에 user_id 없이 **인증 유저 본인 스코프**만 (별도 소유자 검증 불필요한 구조)
- 지역 전환은 **신규 민감 표면 없음**: 자격증명 여전히 미수집, 소급 통화 변환 없음(기존 데이터 불변 — 무결성 리스크 없음)

## 6. 시크릿 관리

- 전 시크릿 `.env` 전용 (`JWT_SECRET`, provider client secret). `.env.example` 만 커밋, 코드/로그/status JSON 기록 금지
- 로그에 토큰·code·이메일 원문 남기지 않음 (마스킹)

## 7. CWE 대응표

| CWE | 항목 | 대응 위치 |
|-----|------|----------|
| CWE-352 | CSRF | OAuth state 서명 토큰 / SameSite=Lax + Origin 검증 |
| CWE-601 | Open Redirect | `next` 상대경로 화이트리스트 |
| CWE-287 | 부적절한 인증 | 이메일 기반 자동 계정 통합 금지 |
| CWE-384 | 세션 고정 | 로그인 시 신규 토큰 세트 발급 |
| CWE-613 | 세션 만료 | Access 30분 / Refresh 14일 + 회전 + 재사용 감지 전체 폐기 |
| CWE-798 / 522 | 자격증명 | 시크릿 .env, provider 토큰 즉시 폐기, refresh 해시 저장 |
| CWE-79 | XSS | httpOnly 쿠키, React 이스케이프, dangerouslySetInnerHTML 금지 |
| CWE-20 / 602 | 입력 검증 | budget/plans 서버 전량 재검증 + region country 열거·currency 서버 매핑·store 국가별 enum |
| CWE-922 | 클라이언트 저장 | localStorage 비식별 데이터만 |
| CWE-307 | 무차별 대입 | auth/budget rate limit |

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 4라운드 보안 검토 반영, 합의 완료)
- 2026-07-09: v1.1 — mealplan 접점 5-1 증보
- 2026-07-09: v1.2 — household/온보딩 접점 5-2 증보
- 2026-07-10: v1.5 — 지역 전환/국가별 스토어 접점 5-4 증보 (country 열거·currency 서버 매핑·본인 스코프)
