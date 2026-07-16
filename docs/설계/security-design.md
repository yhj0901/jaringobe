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

## 5-4. 앱 웹뷰 + 푸시 알림 접점 (v1.5)

**원타임 앱 로그인 코드 (`/auth/app/session`)**
- 코드: 256bit 랜덤, DB 에 SHA-256 해시만(원문 저장 금지), **60초 만료 + 단일 사용**(used_at 마킹)
- 재사용 시도 → 401 동일 에러 + 감사 로그 (만료/위조/재사용 응답 구분 없음 — oracle 차단)
- **CWE-598**: 코드가 URL 쿼리로 이동 — 커스텀 스킴 딥링크는 서버·프록시 로그를 남기지 않음. `app/session` 요청 로그에서 code 마스킹
- **CWE-939**: 커스텀 스킴(`jaringobe://`) 하이재킹 — 악성 앱이 스킴 선점 시에도 코드는 단일사용·60초라 피해 창 최소. **P1 에서 Universal Links(iOS)/App Links(Android) 전환** (도메인 검증 기반 — 스킴 하이재킹 원천 차단)
- rate limit IP 10회/분 (CWE-307). state 에 client 포함해 서명 — 콜백 분기 위조 불가 (CWE-352)

**웹뷰 / 브리지**
- **CWE-345**: 웹뷰는 자사 오리진(`WEB_URL`)만 내부 로드 — 그 외 내비게이션은 시스템 브라우저 위임(`onShouldStartLoadWithRequest`). RN `onMessage` 는 mainFrame origin 검증 후 처리, 웹 쪽은 UA(`JaringobeApp/`) + `window.ReactNativeWebView` 존재 이중 확인 후에만 브리지 활성화
- 브리지로 전달되는 것은 푸시 토큰·권한 상태·명령 열거값만 — 인증 토큰/쿠키를 브리지로 넘기지 않는다 (쿠키는 `app/session` 302 로만 세팅)
- injectedJavaScript 는 UA 마킹·브리지 초기화로 한정 (동적 코드 주입 금지)

**푸시**
- **CWE-359**: 본문은 메뉴명·완료 여부까지만 — 예산액·가구 구성·알레르기 등 금지 (잠금화면 노출 전제). notification_logs 에도 본문 원문 대신 template_key 만 저장
- **CWE-601**: 푸시 `data.path` 는 `/` 시작 상대경로 화이트리스트(기존 next 검증 규칙 재사용) — 앱은 검증 실패 시 홈으로
- **CWE-639**: devices/settings 전부 인증 유저 본인 스코프. 토큰 upsert 시 타 유저 소유 토큰은 현 유저로 이전(기기 재사용 — 이전 소유자에게 오발송 차단)
- **CWE-522**: `EXPO_ACCESS_TOKEN` 은 backend `.env`, 앱 서명 자격증명은 EAS Secrets. 디바이스 토큰은 로그 마스킹
- 로그아웃 시 프론트가 `DELETE /notifications/devices/{token}` 선행 호출 (세션 종료 후 오발송 차단). 스케줄러는 발송 직전 enabled·완료 여부 재확인 (race 방지)
- 규제: 본 범위 알림은 트랜잭션/리마인더 성격 — 광고성 푸시 도입 시 별도 동의 + 야간(21~08시) 제한 선행 (기획서 확정)

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
| CWE-20 / 602 | 입력 검증 | budget/plans 서버 전량 재검증 |
| CWE-922 | 클라이언트 저장 | localStorage 비식별 데이터만 |
| CWE-307 | 무차별 대입 | auth/budget rate limit + app/session IP 제한 |
| CWE-598 | URL 민감정보 | 앱 로그인 코드 60초·단일사용·해시 저장·로그 마스킹 |
| CWE-939 | URL 스킴 검증 | 커스텀 스킴 피해 최소화 + P1 Universal/App Links |
| CWE-345 | 출처 검증 | 웹뷰 오리진 allowlist + 브리지 이중 확인 |
| CWE-359 | 개인정보 노출 | 푸시 본문 메뉴명까지만, logs 는 template_key 만 |

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 4라운드 보안 검토 반영, 합의 완료)
- 2026-07-09: v1.1 — mealplan 접점 5-1 증보
- 2026-07-09: v1.2 — household/온보딩 접점 5-2 증보
- 2026-07-14: v1.5 — 앱 웹뷰+푸시 접점 5-4 증보 (원타임 코드/브리지/푸시, CWE 5종 추가)
