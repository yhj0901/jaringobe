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

## 5-5. 자동주문 P0 접점 (v1.6)

| CWE | 항목 | 요구사항 |
|-----|------|----------|
| CWE-639 | IDOR / 본인 스코프 | 경로에 user_id 없음. preview/POST/latest 전부 인증 유저 본인 행만. 타인 order_id 조회 API 자체를 P0 에 두지 않음 (`GET /orders/{id}` 없음) |
| CWE-20 | 입력 검증 | `store` 는 country 세트 enum. `status`/`frequency`/`line_type` 은 서버가 부여(클라이언트 설정 불가). 수량 Decimal>0 |
| CWE-602 | 클라이언트 검증 의존 금지 | POST 는 라인·가격·matched 를 **받지 않음** (`extra='forbid'`). 서버가 식단+냉장고+build_cart 를 재계산. 프론트 preview 캐시로 확정 금지 |
| CWE-770 | 자원 소모 | preview(네이버+LLM) 기존 store 리미터 **3회/분**. POST 확정 **5회/분**. GET latest 리미터 없음. 프론트 버튼 비활성 |
| CWE-522 | 자격증명 보호 | `orders`/`order_items` 에 스토어 시크릿·쿠키·토큰 컬럼 금지. Naver 키는 기존 `.env` 만. 로그에 키·장바구니 링크 쿼리 시크릿 금지 |
| CWE-79 | XSS | 상품 title/mallName 은 네이버 HTML 태그 기존 스트립 유지 + React 이스케이프. **link 는 https 만 허용**(그 외 저장·렌더 null). `dangerouslySetInnerHTML` 금지 |

- **정직 표시**: `simulation: true` 고정. `paid`/`charged` 상태값 도입 금지. 가짜 승인번호·카드 마스킹 영수증 생성 금지
- 게스트 주문 persist 금지. 확정 inbound 는 서버 내부 `fridge.add_items` 만 (프론트 이중 POST 로 source 위조 여지 차단)
## 5-6. 주간 자동 사이클 접점 (v1.8 — 루프완결-주간사이클)

> 기획 8장 승계 + 설계 확정 사항. 신규 표면: 서버 스케줄러가 **사용자 개입 없이** 식단을 생성하고 주문을 확정하고 냉장고를 변경한다.

| CWE | 항목 | 요구사항 |
|-----|------|----------|
| **CWE-639** | IDOR / 본인 스코프 | `/cycle*`·`/orders/{id}/*` 전부 경로에 `user_id` 없음 — 인증 유저 본인 행만. `{id}` 를 받는 3종(`approve`/`cancel`/`delivery`)은 **소유자 검증 후 403 `FORBIDDEN`**. **스케줄러도 예외가 아니다** — due 스캔이 대상 행을 고른 뒤의 모든 조회·변경은 반드시 그 `user_id` 로 스코프한다. 배치라는 이유로 전역 쿼리를 쓰면 그 자체가 IDOR |
| **CWE-602** | 클라이언트 검증 의존 금지 | `POST /orders/{id}/approve` 는 라인·가격·`matched` 를 **받지 않는다**(`extra='forbid'`). 서버가 식단+냉장고+시세를 재계산한다. 프론트 preview 캐시로 확정 금지. `excludeNames`(P1)는 **이름만** 받고 가격·수량은 서버 값 사용 |
| **CWE-841** | 부적절한 상태 전이 | 주문 상태 머신을 애플리케이션에서 강제: `draft → awaiting_user → confirmed → cancelled` / `draft\|awaiting_user → expired` / `* → failed`. **`confirmed → draft` 역행 금지**, `inbound_at IS NOT NULL` 인 주문 재확정 금지. 위반은 `409 ORDER_INVALID_STATE`. 배송 상태(`delivery_state`)를 `status` 와 **별도 축**으로 분리해 상태 머신 오염을 막는다 |
| **CWE-367** | TOCTOU / 경합 | 자동확정 게이트 판정과 저장 사이에 사용자가 수동 확정할 수 있다 → **부분 유니크 인덱스가 최종 방어선**(`uq_orders_confirmed_cycle`). 게이트 통과만으로 안전하다고 가정하지 않는다. `IntegrityError` 는 **정상 스킵**으로 처리하고 사용자에게 에러 알림을 보내지 않는다 |
| **CWE-770** | 자원 소모 | 자동 생성: 사용자당 사이클 1회 + 전체 일일 상한(FR-817, architecture 3-9-10). 사용자 요청: `/cycle/settings`·`/cycle/skip`·`approve`·`cancel`·`delivery` **5회/분**, `preview?refresh=true` **3회/분**(기존 store 리미터). **스케줄러 자신에게도 상한을 적용** — 사용자별 결정적 지터(0~30분)로 동시 폭주를 막아 스스로 rate limit 을 치지 않게 한다 |
| **CWE-522** | 자격증명 보호 | `user_cycle_settings`·`orders` 에 스토어 시크릿·쿠키·토큰 컬럼 **금지**. 네이버·Expo 키는 `.env` 만. 장바구니 링크의 쿼리 파라미터를 로그에 남기지 않는다 |
| **CWE-359** | 개인정보 노출 | 푸시 본문에 **예산액·금액·가구 구성·건강(알레르기) 정보 금지** — 잠금화면 전제. "장바구니가 준비됐어요" 수준까지만, 상세는 앱을 열어야 보이게 한다. `notification_logs` 는 본문 원문 대신 `template_key` 만 기록(기존 정책 승계) |
| **CWE-601** | 오픈 리다이렉트 | 알림 딥링크 `data.path` 는 **내부 상대경로 화이트리스트**만: `/orders`, `/fridge`, `/mealplan/{id}`. 외부 URL·커스텀 스킴 차단 |
| **CWE-20** | 입력 검증 | `frequency`(weekly\|biweekly), `anchorWeekday`(0~6), `timezone`(**IANA 화이트리스트** `zoneinfo.available_timezones()`), `received`(boolean), `excludeNames`(≤40개·각 ≤200자). `status`·`simulation`·`lineType`·`cycleStart`·`deliveryEta`·`autoConfirmAt` 은 **서버가 부여**하며 클라이언트가 설정할 수 없다. `POST /cycle/skip` 은 대상 사이클을 body 로 받지 않는다(과거 사이클 조작 표면 제거) |
| **CWE-532** | 로그 민감정보 | 구조화 로그에 `user_id`·`stage`·`reason`·`cycle_start` 만. **금액·재료명·가구 구성·예산액 금지** |
| **CWE-79** | XSS | 상품 `title`/`mallName` 은 기존 HTML 태그 스트립 + React 이스케이프 유지. `link` 는 **https 만** 저장·렌더 (v1.6 정책 승계) |

### 자동화 특유의 보안 판단 (v1.8)

- **정직 표시 (US-814)**: `simulation=true` 고정. `paid`/`charged` 상태값 도입 **금지**. 가짜 승인번호·영수증 생성 금지. 자동확정 알림·화면에도 "연동 표시 기준 시뮬레이션 (실결제 아님)" / EN 동등 문구를 유지한다. `CycleState.simulation` 을 응답 계약에 고정 필드로 둔 것은 프론트가 이 고지를 빠뜨릴 수 없게 하기 위함이다.
- **"자동으로 돈을 쓰는 시스템"의 신뢰 경계**: 현재는 시뮬레이션이므로 자동확정이 금전 손실을 만들지 않는다. **실결제 도입 시점에 자동확정 로직을 그대로 켜두면 안 된다.** 실결제 전환은 ① 자동확정에 대한 **별도 명시 동의**(약관 + 앱 내 재확인) ② 1회 상한액 ③ 확정 후 N시간 취소 가능 기간 ④ 결제 실패 재시도 정책을 **선행 조건**으로 하며, 실결제 기획의 GATE 항목으로 이관한다.
- **예산 락은 자동화가 넘을 수 없는 선이다**: `locked=true` 인 사용자는 한도를 넘는 자동확정이 **불가능**하다(게이트 ⑤). `locked=false` 는 사용자가 명시적으로 해제한 상태이므로 경고만 하고 통과시킨다 — 시스템이 사용자의 명시적 결정을 대신 뒤집지 않는다.
- **스케줄러 실행 권한**: 스케줄러는 HTTP 요청 컨텍스트가 없으므로 인증 미들웨어를 거치지 않는다. 따라서 **서비스 계층이 `user_id` 를 인자로 강제**하는 구조를 유지한다(전역 세션·암묵적 현재 사용자 개념을 만들지 않는다).
- **멀티 인스턴스**: 단일 인스턴스 전제(architecture 3-9-3). 중복 실행은 보안 문제는 아니지만 **자원 소모(CWE-770)** 이슈이므로 배포 형상 제약으로 문서화한다.

### 규제

| 항목 | 요구사항 |
|------|----------|
| 정보통신망법 | 본 설계의 알림 3종(`order_approval`/`fridge_inbound`/`cycle_paused`)은 사용자가 설정한 **트랜잭션 알림**으로 광고성 정보가 아니다. **광고성 푸시 도입 시** 별도 명시 동의 + 야간(21~08시) 전송 제한 체계가 선행되어야 한다 |
| GDPR/CCPA | 주문 이력 24개월 보관 후 배치 삭제(v1.6 승계), 발송 이력 90일, 디바이스 토큰은 계정 삭제 시 즉시 파기. `user_cycle_settings`·`fridge_items.order_id` 는 `users` CASCADE / `orders` SET NULL 로 탈퇴 시 정리된다 |
| 개인정보 최소화 | `users.last_seen_at` 은 활성 판정 목적의 **단일 타임스탬프**이며 접속 이력을 누적하지 않는다(행동 로그가 아니다). `last_generated_at` 도 마지막 1건만 보관 |

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
| CWE-639 | IDOR | order preview/POST/latest 본인 스코프, `/orders/{id}` 미제공 (v1.6) |
| CWE-770 | 자원 소모 | order preview 3/분(store 재사용) · POST 5/분 (v1.6) |

## 변경 이력
- 2026-08-15: **v1.6** — 자동주문 P0 접점 5-5 (CWE-639/20/602/770/522/79). simulation=true, paid 상태 없음, 주문 테이블에 스토어 시크릿 없음, 상품 링크 https-only. 설계 토론 5라운드 합의
| CWE-841 | 상태 전이 | 주문 상태 머신 강제, `confirmed→draft` 역행 금지 (v1.8) |
| CWE-367 | TOCTOU | 자동확정 게이트 ↔ 수동 확정 경합 — 부분 유니크 인덱스가 최종 방어선 (v1.8) |
| CWE-532 | 로그 민감정보 | 사이클 구조화 로그에 금액·재료명·가구 구성 금지 (v1.8) |

## 변경 이력
- 2026-08-30: **v1.8** — 주간 자동 사이클 접점 5-6 (CWE-639/602/841/367/770/522/359/601/20/532/79). 스케줄러도 user_id 스코프 강제, 자동확정 5중 게이트, 부분 유니크 = TOCTOU 최종 방어선, 푸시 본문 금액·가구 구성 금지, 실결제 전환 선행 조건 이관. 설계 토론 5라운드 합의
- 2026-07-09: 최초 작성 (설계 토론 4라운드 보안 검토 반영, 합의 완료)
- 2026-07-09: v1.1 — mealplan 접점 5-1 증보
- 2026-07-09: v1.2 — household/온보딩 접점 5-2 증보
- 2026-07-10: v1.5 — 지역 전환/국가별 스토어 접점 5-4 증보 (country 열거·currency 서버 매핑·본인 스코프)
