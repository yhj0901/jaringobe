# 보안 가이드 (인증/세션/자동화)

> 원본: `docs/설계/security-design.md` (v1.9, CWE 대응표 포함) + QA 결과 `docs/테스트/보안테스트.md` (2026-09-05 재판정: 26건 중 24 PASS / 주의 2(Low) / FAIL 0). 기준 시점: v0.2.0.

## 인증 흐름 요약
- 소셜 로그인은 **백엔드 주도 Authorization Code**: 브라우저 → `GET /auth/{provider}/authorize` → provider 동의 → 백엔드 `/callback` 이 토큰 교환·유저 upsert·쿠키 세팅 → 프론트 302. 시크릿·provider 토큰은 서버 밖으로 나가지 않고, provider access token 은 프로필 조회 후 폐기
- 계정 정책: **provider별 별도 계정** — 동일 이메일이어도 자동 통합 금지 (CWE-287), notice 안내만
- **앱 로그인 (웹뷰)**: `authorize?client=app` 의 `client` 가 OAuth `state` 서명에 포함된다(콜백 분기 위조 차단, CWE-352). 콜백은 쿠키 대신 **원타임 코드**를 `{APP_SCHEME}://auth?code=` 딥링크로 전달하고, 앱이 웹뷰에서 `GET /auth/app/session?code=` 로 교환한다. 코드는 256bit 랜덤, DB 에는 **SHA-256 해시만**(`app_login_codes.code_hash`), 60초 만료·단일 사용, 실패 사유는 구분 없이 `AUTH_INVALID_APP_CODE`(oracle 차단). `/auth/*` IP 10회/분 리미터가 함께 적용
- `users.last_seen_at` 은 인증 쓰기 경로 3곳(OAuth 콜백 / refresh / app session)에서만 갱신 — 읽기 요청마다 UPDATE 하지 않는다(쓰기 폭증 방지). 활성 판정 목적의 단일 타임스탬프이며 접속 이력을 누적하지 않는다(개인정보 최소화)

## 토큰/쿠키 정책 (구현: `backend/app/core/security.py`)

| 항목 | 값 |
|------|-----|
| Access | JWT HS256, 30분, `jaringobe_access` 쿠키 |
| Refresh | 랜덤 256bit, 14일, DB 엔 SHA-256 해시만, `jaringobe_refresh` 쿠키 `Path=/api/v1/auth` |
| 쿠키 공통 | HttpOnly + SameSite=Lax (+ `COOKIE_SECURE=true` 시 Secure — **배포 필수**) |
| 회전 | refresh 사용 시 revoke+재발급, `rotated_from` 체인. **재사용 감지 시 유저 전 세션 폐기** |
| 앱 로그인 코드 | `secrets.token_urlsafe(32)`, SHA-256 해시 저장, 60초(`app_login_code_expire_seconds`) |

## 요청 방어 (구현: `backend/app/main.py`, `core/ratelimit.py`)

### Origin 검증과 "GET 부작용 금지" 원칙 (CWE-352 / CWE-650)
- 미들웨어 `verify_origin` 은 **`POST/PUT/PATCH/DELETE`**(`_STATE_CHANGING_METHODS`) 에서 Origin 헤더가 존재하는데 `FRONTEND_ORIGIN` 과 불일치하면 403 `FORBIDDEN_ORIGIN` (부재 시 통과 — SameSite=Lax 가 1차 방어)
- 이 방어는 **GET/HEAD 핸들러가 부작용을 갖지 않는다는 전제** 위에서만 성립한다. 브라우저는 최상위 내비게이션 GET 에 Origin 을 보내지 않고 SameSite=Lax 쿠키는 붙이므로, GET 에 Origin 검증을 추가해도 링크 클릭 CSRF 는 못 막는다
- **사례(v1.9 에서 해소)**: `GET /orders/preview?refresh=true` 가 저장 초안을 갱신 저장하는 GET 이었다 → `refresh` 파라미터를 제거하고 `POST /orders/{id}/recalculate` 로 메서드를 옮겼다. QA H-13(`?refresh=true` 가 행·라인·`updated_at` 을 바꾸지 않음) · H-08(`recalculate` Origin 불일치 403) PASS
- **일반 규칙(리뷰 체크리스트)**: GET/HEAD 핸들러는 DB 쓰기·외부 호출 부작용을 갖지 않는다. 유일한 예외는 최초 호출 시 **멱등한 기본값 행 생성**(`GET /cycle`·`GET /notifications/settings` 의 lazy 생성). 사용자 데이터 **값을 바꾸는** GET 은 금지

### Rate limit (인메모리 슬라이딩 윈도우 — 멀티 인스턴스 시 Redis 교체 필요)
| 대상 | 한도 | 키 |
|------|------|-----|
| `/api/v1/auth/*` | 10회/분 | IP |
| `POST/PUT /budget/plans`, `POST /mealplans` 계열 | 5회/분 | 유저 |
| `POST /store/cart`, `POST /mealplans/monthly` | 3회/분 | 유저 (네이버+LLM 비용) |
| `GET /orders/preview` **즉석 계산만**(저장 초안 없음), `POST /orders/{id}/recalculate` | 3회/분 | 유저 (`order_preview_user_limiter`). 저장 초안 스냅샷 조회는 외부 호출이 없어 미적용 |
| `POST /orders` | 5회/분 | 유저 (`order_confirm_user_limiter`) |
| `PUT /cycle/settings` · `POST /cycle/skip` · `POST /orders/{id}/approve|cancel|delivery` | 5회/분 **공유 버킷** | 유저 (`cycle_action_user_limiter`) — 스펙은 엔드포인트별. 보안상 더 엄격하므로 취약점은 아니나 UX 결함(BUG-007, Low). 코드 주석 "10회/분" 도 실제 5 와 불일치 |
| `PUT /notifications/devices` · `PUT /notifications/settings` | 10회/분 **엔드포인트별** | 유저 |
| 스케줄러 자신 | 사용자당 사이클 1회 + 일일 200건, 사용자별 결정적 지터 0~30분, 초안 실패 1/5/15분 백오프 | — (CWE-770) |

### 입력 검증 (CWE-20 / CWE-602)
- 클라이언트 값 불신: `POST /orders`·`/approve` 는 라인·가격·`matched` 를 **받지 않는다**(`extra='forbid'` → 422). 서버가 식단+냉장고+시세를 재계산. `excludeNames` 는 이름만(≤40개, 각 1~200자), 가격·수량은 서버 값
- `received` 는 `StrictBool`(`"yes"`/`"true"`/`1`/`0`/`None` 전부 422, BUG-009). `timezone` 은 `zoneinfo.available_timezones()` 화이트리스트. `anchorWeekday` 0~6, `frequency` enum, `store` 는 `user.country` 세트(그 외 404)
- `status`·`simulation`·`lineType`·`cycleStart`·`deliveryEta`·`autoConfirmAt` 은 **서버가 부여**. `POST /cycle/skip` 은 대상 사이클을 body 로 받지 않는다(과거 사이클 조작 표면 제거)
- 게스트 이전 입력은 서버 전량 재검증 (localStorage 변조 대비)

## 자동화(스케줄러)의 보안 경계 — v1.8
| CWE | 요구사항 | 구현 지점 |
|-----|----------|-----------|
| **CWE-639** IDOR | `/cycle*`·`/orders/{id}/*` 는 경로에 `user_id` 없음, `{id}` 4종은 소유자 검증 후 403. **스케줄러도 예외가 아니다** — due 스캔이 대상 행을 고른 뒤의 모든 조회·변경은 그 행의 `user_id` 로 재스코프. 배치라는 이유로 전역 쿼리 금지 | `cycle/scheduler.py`(`mark_inbound(db, order.user_id, order.id)`), `order/service._owned_order` |
| **CWE-841** 상태 전이 | `draft → awaiting_user → confirmed → cancelled` / `draft\|awaiting_user → expired` / `* → failed` / `failed → ∅`. `confirmed → draft` 역행·`inbound_at` 있는 주문 재확정 금지 → 409 `ORDER_INVALID_STATE`. `delivery_state` 를 `status` 와 별도 축으로 두어 상태 머신 오염 방지 | `order/service.transition_order`, `_ALLOWED_TRANSITIONS` |
| **CWE-367** TOCTOU | 자동확정 게이트 판정과 저장 사이에 수동 승인이 끼어들 수 있다 → **부분 유니크 인덱스 `uq_orders_confirmed_cycle` 가 최종 방어선**. `IntegrityError` 는 정상 스킵(에러 알림 없음). 동시 승인 3회 → 확정 1건(`FOR UPDATE` 직렬화), 수동×자동 동시 → 1건 | QA S2-03/04, H-38 |
| **CWE-770** 자원 소모 | 위 리미터 표 + 스케줄러 자기 상한. 초안 실패 시 백오프·4회차 폴백으로 네이버 재호출 폭주 방지(BUG-002 수정). 잔여: D-1 재계산 시세 실패 시 매 tick 재시도(BUG-012, Low — 설계 결정 대기) | `cycle/service._process_draft_stage`, `policy.draft_retry_delays_minutes` |
| **CWE-522** 자격증명 | `user_cycle_settings`·`orders`·`order_items`·`device_tokens` 에 스토어 시크릿·쿠키·토큰 컬럼 없음. 네이버·Expo 키는 `.env` 만. Expo 토큰은 발송 주소(비밀 아님)지만 로그는 마스킹(`mask_token`) | 스키마 대조, QA S-29 |
| **CWE-359** 개인정보 | 푸시 본문에 **예산액·금액·가구 구성·알레르기 금지**(잠금화면 전제). 3종 템플릿 본문 숫자 0개. `notification_logs` 는 `template_key` 만 | `notification/sender.py::TEMPLATES`, QA S-28 |
| **CWE-601** 오픈 리다이렉트 | 푸시 `data.path` 는 `/orders`·`/fridge`·`/mealplan/{id}` 화이트리스트만(`build_message` 가 그 외 `ValueError`). `next` 파라미터·앱 `next` 도 상대경로 화이트리스트 | `sender._SAFE_PATH`, `sanitize_next_path` |
| **CWE-532** 로그 | 사이클 구조화 로그(`_log_transition`)는 `user_id`·`stage`·`reason`·`cycle_start` 만 — 금액·재료명·가구 구성 금지. (단 앱 로거가 미구성이라 실제로는 미출력 — BUG-011, 운영 전 필수) | `cycle/service._log_transition` |
| **CWE-209/200** 정보 노출 | preview `notes` 는 사유 코드(`PRICE_LOOKUP_UNAVAILABLE`)만 — `.env` 변수명 안내 제거(BUG-008). 422 응답에 스택·경로 없음 | QA H-46~48, R-09 |
| **CWE-79** XSS | 상품 `title`/`mallName` 은 HTML 태그 스트립 + React 이스케이프, `link` 는 **https 만** 저장(비-https → null). 프론트 `dangerouslySetInnerHTML` 0건 | QA S1-13, S-26 |
| **CWE-89** | `excludeNames` 등 전부 파라미터 바인딩 | QA H-34 |

### 자동화 특유의 판단
- **정직 표시 (US-814)**: `simulation=true` 고정(`CycleState.simulation` 은 계약 고정 필드), `paid/charged` 상태·가짜 승인번호·영수증 금지. 자동확정 알림·화면에도 "연동 표시 기준 시뮬레이션 (실결제 아님)" 유지
- **예산 락은 자동화가 넘을 수 없는 선**: `locked=true` 사용자는 재계산 총액이 `cycle_limit` 을 넘으면 확정·`delivery_eta`·inbound **이전**에 `awaiting_user/BUDGET_EXCEEDED` 로 차단된다(BUG-001 수정, QA R-01a~g 락 사용자 초과 `confirmed` 0건). `locked=false` 는 사용자의 명시적 해제이므로 경고만 하고 통과. 유일한 초과 확정 경로는 사용자의 명시 승인(`approve`/`POST /orders`)뿐이며 기획상 허용
- **실결제 전환 시 자동확정을 그대로 켜두면 안 된다**: 별도 명시 동의 · 1회 상한액 · 취소 유예 · 결제 실패 재시도 정책이 선행 조건(실결제 기획 GATE 항목으로 이관)
- **멀티 인스턴스**: 단일 인스턴스 전제(architecture-guide). 중복 실행은 보안 문제는 아니지만 CWE-770 이슈 — `CYCLE_SCHEDULER_ENABLED` 는 1대만 true
- **규제**: 알림 3종(`order_approval`·`fridge_inbound`·`cycle_paused`)은 사용자가 설정한 트랜잭션 알림(광고성 아님). 광고성 푸시 도입 시 별도 동의 + 야간(21~08시) 제한 선행. 주문 24개월·발송 이력 90일 보관, 디바이스 토큰은 계정 삭제 시 CASCADE 파기

## 개발 시 지켜야 할 것
- 시크릿은 `.env` 만 (`JWT_SECRET`, provider secret, `NAVER_*`, `EXPO_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`) — 코드/로그/status JSON 기록 금지. 에러 `notes`·메시지에 환경변수명을 노출하지 않는다
- 로그에 토큰·code·이메일·금액·재료명 원문 금지
- 프론트: localStorage 에 PII/토큰 저장 금지(게스트 키 `jaringobe.guest.v1`, 휴면 카드 억제 키, 푸시 soft-ask 마커는 비식별 데이터만), `dangerouslySetInnerHTML` 금지. 파생 상태(`stage`·`blockedReason`)는 서버 값 그대로 — 클라이언트 추론은 서버와 어긋나는 순간 거짓 정보
- `next` 류 리다이렉트 파라미터·푸시 `path` 는 항상 상대경로 화이트리스트 (CWE-601)
- **rollback 후 ORM 인스턴스에 접근하지 말 것** — `MissingGreenlet`/만료 인스턴스로 예외 핸들러 자체가 죽어 백오프·정리 로직이 무력화된다(BUG-002·005 공통 원인). 식별자를 try 이전에 보관하고 재조회한다(후속 R-6 리뷰 체크리스트)
- 새 GET 엔드포인트가 DB 를 쓰거나 외부를 호출하면 설계 재검토(위 "GET 부작용 금지")
- 새 스케줄러 스캔은 partial index + `FOR UPDATE SKIP LOCKED` + 대상 행 `user_id` 재스코프 + 재실행 안전(멱등) 증명을 먼저

## 배포 시 필수 (미해결 권고 R-1·R-2·R-7)
- `COOKIE_SECURE=true`, `FRONTEND_ORIGIN` = 실제 프론트 도메인 (https). 로컬로 돌아올 때 `false`/`http://localhost:3000` 복원
- 멀티 인스턴스 배포 시 인메모리 리미터 → Redis, `CYCLE_SCHEDULER_ENABLED`·`REMINDER_SCHEDULER_ENABLED` 1대만 true
- **`app` 로거 INFO 출력 + 구조화 포맷 구성(BUG-011)** — 없으면 BUG-002 류 장애가 운영에서 감지되지 않는다
- 실키(`KAKAO_*`/`GOOGLE_*`/`NAVER_*`/`ANTHROPIC_API_KEY`/`EXPO_ACCESS_TOKEN`) 확보 후 BLOCKED 5항목 스테이징 재검증(R-8)
