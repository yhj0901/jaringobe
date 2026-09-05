# i18n 가이드 (ko/en)

> 스택: next-intl, 로캘 프리픽스 라우팅 (`/ko/...`, `/en/...`, 기본 ko). 원본 설계: `docs/설계/ui-design.md` 6장·14-6. 기준 시점: v0.2.0 (2026-09-05).

## 철칙
1. **UI 문자열 하드코딩 금지** — 모든 노출 텍스트는 `frontend/messages/{ko,en}.json` 키
2. **ko.json / en.json 동시 수정** — 키 집합 동치가 테스트로 강제됨 (`src/i18n/__tests__/messages.test.ts`, 불일치 시 CI 실패). QA 는 추가로 플레이스홀더 동치·빈 값·en 값 한글 잔존·하드코딩 스캔을 확인한다(2026-09-05 전부 PASS)
3. **API 는 노출 문구를 내리지 않는다** — 에러 `detail.code` 를 프론트가 `{domain}.error.{code}` 로 매핑, 미정의 코드는 `common.error.fallback`. 서버 사유 코드(`blockedReason`, preview `notes`)도 같은 방식으로 키 매핑
4. **푸시 본문은 프론트가 만들지 않는다** — 원본은 백엔드 `notification/sender.py::TEMPLATES`(ko/en, `device_tokens.locale` 기준). 프론트 `notification.*` 키는 설정 화면 타입 라벨·인앱 배너용이다(이중 관리 금지)

## 키 체계
```
{domain}.{화면/컴포넌트}.{요소}
예) cycle.stage.awaitingUser.title / cycle.blocked.BUDGET_EXCEEDED.cta / orders.status.draft / notification.orderApproval.title
```

### 현재 규모 — ko/en 각 **567 키** (v0.1.0 91 → main 356 → v0.2.0 567, 이번 범위 +211)

| 네임스페이스 | 키 수 | 이번 범위 | 용도 |
|--------------|------:|-----------|------|
| `cycle` | 80 | 신규 | 홈 사이클 카드·설정 카드·휴면 복귀 카드 |
| `orders` | 64 | 신규(P0 + 사이클 확장) | `/orders` 리뷰·6상태·승인/재계산/취소 |
| `notification` | 27 | 신규 | 알림 설정 라벨·인앱 배너·soft ask |
| `memberHome` | 79 | +20 (`memberHome.autoOrder.*`) | 회원 홈 자동주문 카드 |
| `settings` | 67 | +6 | 알림·자동 주문 섹션 |
| `fridge` | 7 | 신규 (`fridge.delivery.*`, `fridge.expiring.nextPlanHint`) | 배송 확인 시트 |
| `fridgePage` | 18 | +3 | |
| `metadata` | 10 | +4 | 라우트 메타 |
| 기타 (`guestHome` 52 · `onboarding` 66 · `auth` 24 · `mealplan` 21 · `budgetDraft` 19 · `store` 12 · `memberType` 10 · `cuisine` 6 · `entry` 4 · `common` 1) | 215 | 변경 없음 | 게스트 키(`guestHome.*`)는 변경 금지 |

### 이번 범위 주요 키 (설계 14-6)
```
cycle.card.title
cycle.stage.{idle|generating|generated|generateFailed|drafted|awaitingUser|confirmed|delivered
             |nothingToOrder|skippedUser|skippedDormant|deferredQuota|paused}.{title,body}
cycle.stage.drafted.autoConfirmAt            // "{time}에 자동으로 확정돼요"
cycle.stage.delivered.body                   // "{completed}/{total}" — mealPlan.completedMealCount/mealCount
cycle.blocked.{BUDGET_EXCEEDED|UNMATCHED_RATIO|STORE_DISCONNECTED|AUTO_CONFIRM_OFF|US_NO_PRICE|MEALPLAN_OVER_BUDGET}.{title,cta}
cycle.cta.{approve|view|skip|createNow|dismiss|goSettings|cancelOrder}
cycle.dormant.{title,body,cta}               // 휴면 복귀 1회 카드
cycle.settings.{section,enabled,frequency,frequencyWeekly,frequencyBiweekly,frequencyUsHint,biweeklyGraceHint,
                anchorWeekday,autoConfirm,autoConfirmOffHint,autoConfirmPushNotice,timezone}
cycle.weekday.{0..6}                         // 0=일요일 (JS getDay 규약, 서버 anchorWeekday 와 동일)
cycle.error.{CYCLE_ALREADY_CONFIRMED|RATE_LIMITED}

orders.status.{draft|awaitingUser|confirmed|cancelled|expired|failed}
orders.simulationNotice                      // "연동 표시 기준 시뮬레이션 (실결제 아님)" — 확정 화면 3곳
orders.autoConfirmedBadge / orders.recalculatedNotice / orders.alreadyConfirmed
orders.deliveryEta                           // "{date} 도착 예정"
orders.recalculateCta / orders.recalculating // awaiting_user 재계산(POST recalculate)
orders.terminal.failed.body                  // 다음 사이클 안내 — "다시 계산" 언급 없음(failed 는 터미널)
orders.error.{ORDER_INVALID_STATE|ORDER_ALREADY_CONFIRMED|ORDER_CANCEL_WINDOW_CLOSED|STORE_NOT_CONNECTED|NOTHING_TO_ORDER|MEALPLAN_NOT_FOUND|ORDER_NOT_FOUND|RATE_LIMITED}

fridge.delivery.{title,body,yes,adjust,notYet,unknownBanner}   // "받으셨나요?" 시트
notification.{orderApproval|fridgeInbound|cyclePaused}.{title,body}
settings.notifications.type.{orderApproval|fridgeInbound|cyclePaused}
```

신규 키 추가 절차: 양쪽 json 에 같은 키 추가 → `npm run test`(키 동치 테스트) → 플레이스홀더(`{time}` 등)가 양쪽에 같은지 확인.

## 금액·날짜 표기
- 금액은 `Money = {amount: string, currency: 'KRW'|'USD'}` 그대로 받아 **`MoneyText`/`formatMoney`** (`Intl.NumberFormat(ko-KR|en-US, currency)`) 로만 렌더 — 직접 포맷 금지, float 변환 금지(Decimal 문자열 그대로 전달)
- 시각은 API 가 UTC(Z) — 이번 범위부터 **시각 노출이 생겼다**(`nextRunAt`·`autoConfirmAt`·`deliveryEta`). `Intl.DateTimeFormat(ko-KR|en-US)` 로 사용자 로컬 변환해 표시하고, 서버 타임존(`CycleState.timezone`)은 설정 카드에 표시만 한다(변경 UI 는 BUG-010 후속)
- 날짜 필드(`cycleStart` 등 `YYYY-MM-DD`)는 사용자 로컬 date 이므로 타임존 변환 없이 표시

## 로캘별 분기 데이터
- 소셜 버튼 순서: ko 카카오 우선 / en 구글 우선·카카오 최하단 (`SocialLoginButtons`)
- 예산 프리셋: ko 30/50/70/100만원 / en $300~1000 (`shared/config/constants.ts`)
- 샘플 매트릭스: `features/guest/sample-matrix/{ko,en}.json`
- 국가별 스토어 세트: KR kurly·coupang·ssg·naver / US walmart·instacart (`store.*`). US 는 시세가 없으므로 `orders.noPrice`·`cycle.blocked.US_NO_PRICE` 경로가 항상 쓰인다
- 주기 안내: US 는 `cycle.settings.frequencyUsHint`(주 1회 권장 문구), biweekly 는 `biweeklyGraceHint`(그레이스 12h)
- 푸시 템플릿(백엔드): `push.orderApproval` "이번 주 장바구니가 준비됐어요" / "Your weekly cart is ready" 등 3종 — 본문에 금액·가구 구성 금지(CWE-359). 끼니 라벨은 `MEAL_TYPE_LABELS`
- SEO 메타: 로캘별 generateMetadata + hreflang (`app/[locale]/layout.tsx`)

## 알려진 갭
- `CycleSettingsCard` 의 타임존은 **표시만**(BUG-010, Low) — 서버 `PUT /cycle/settings {timezone}` 은 동작하므로 UI 추가 시 `cycle.settings.timezone` 키 재사용
- 앱(`mobile/`) 자체 문자열은 이 체계 밖(웹뷰가 웹 문자열을 그대로 표시)
