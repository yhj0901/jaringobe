# UI 설계서 — 게스트 홈 + 로그인

> 대상 기획: `docs/기획/게스트홈-진입경험.md`, `docs/기획/로그인-소셜인증.md`
> 스택: Next.js 14+ App Router / TypeScript strict / Tailwind CSS / next-intl (ko/en)

## 1. 라우트 구조 (`src/app/[locale]/`)

| 라우트 | 렌더링 | 설명 |
|--------|--------|------|
| `/` | SSG 셸 + 클라이언트 게스트 로직 | 홈 — 게스트/회원 공용 셸. 회원 여부는 서버에서 쿠키로 판정해 데이터 소스 결정 |
| `/login` | RSC | 로그인 페이지. `?error={code}`·`?notice={code}` 를 i18n 매핑해 배너 표시 |
| `/onboarding` | RSC + 클라이언트 | 라우트 예약 (본 구현은 household 기획). 게스트 이전 성공 시 확인 화면 1장만 이번 범위 |
| `/orders` | RSC + 클라이언트 | **v1.7 (자동주문 P0)** 장바구니 리뷰. 보호 라우트 — 미인증 시 `/login?next=/orders` |
| 미들웨어 | - | 로캘 프리픽스(next-intl) + 보호 라우트(`/onboarding`, `/settings`, **`/orders`**) 미인증 시 `/login?next=` 리다이렉트 |

- 로캘 라우팅: `/ko/...`, `/en/...` — 기본 `ko`, `Accept-Language` 기반 최초 감지

## 2. 컴포넌트 트리 (홈 셸 = 게스트/회원 공유)

```
app/[locale]/page.tsx (RSC)
└─ features/home/HomeShell            ← 데이터 주입형: props로 HomeViewModel 수신
   ├─ TrialModeBadge                  ← 게스트일 때만 ("체험 모드")
   ├─ BudgetMoodCard                  ← 남은 예산·절약·폐기 절감 (Money 표시)
   ├─ MealPlanSection
   │   └─ MealCard × 3 (아침/점심/저녁, "예시" 라벨 슬롯)
   ├─ FridgePreviewCard               ← 냉장고 위젯 (임박 배너 포함)
   └─ AutoOrderCard                   ← 비활성/활성 상태 (활성 시 CTA)
features/guest/
   ├─ GuestHomeController (client)    ← localStorage 복원 → HomeViewModel 생성/갱신
   ├─ EngagementPrompt (client)       ← 체류 10초+스크롤 유휴 감지 → BottomSheet
   ├─ BudgetDraftFlow (client)        ← 3스텝 오버레이 (인원 → 예산 → 식단 방향)
   ├─ PersistentCtaBanner             ← "아니오" 이후 상단 상시 CTA
   └─ sample-matrix/ (ko.json, en.json)
features/auth/
   ├─ SocialLoginButtons              ← 로캘별 순서/노출, 브랜드 가이드 준수
   ├─ SignupGateModal                 ← 쓰기 행동 공통 게이트 (FR-109)
   └─ useSession / requireAuth        ← GET /users/me 래핑
features/budget/
   └─ importGuestPlan()               ← POST /budget/plans + 성공/409/422 분기 (FR-108)
shared/ui/ BottomSheet, Badge, MoneyText(통화 로캘 포맷), Stepper
shared/config/ constants.ts           ← PROMPT_DWELL_MS=10000 등 상수 분리
```

**HomeViewModel (셸 주입 계약)** — 게스트 샘플과 회원 실데이터가 같은 형태로 주입됨:
```ts
interface HomeViewModel {
  mode: 'guest-default' | 'guest-planned' | 'member';
  budgetMood: { remaining: Money; saved: Money; wastePrevented: Money };
  weekPlan: DayPlan[];          // MealCard 데이터 (isSample: boolean)
  fridgePreview: FridgeItem[];
  autoOrder: { active: boolean; nextOrderDate?: string; stores: StoreBadge[] };
}
type Money = { amount: string; currency: 'KRW' | 'USD' };  // 문자열 — float 금지
```

## 3. 게스트 상태 관리

- **zustand + persist** (`jaringobe.guest.v1`): `{ plan?: {householdSize, amount, currency, mealDirection}, promptHistory, savedAt }` — 30일 만료 검사 후 복원, 스키마 version 필드로 마이그레이션 대비
- 서버 상태(users/me 등)는 RSC fetch + 최소 클라이언트 훅 — 전역 서버상태 라이브러리는 현 범위 미도입
- 샘플 매트릭스: `가구 구간(1/2/3-4/5+) × 예산 구간 × 식단 방향(4) × 로캘` → `HomeViewModel` 부분값. 금액은 문자열+통화 (설계 시 초기 데이터셋은 콘텐츠 산출물로 별도 작성 — 구현 에이전트에 파일 스키마만 계약)

## 4. 타이밍 프롬프트 동작 규칙 (FR-102/103)

```
조건: 페이지 가시 상태 누적 10초(PROMPT_DWELL_MS) AND 스크롤 유휴 1.5초 AND 세션 내 미노출
  → BottomSheet "예산안을 작성해 보시겠어요?" [예 / 아니오]
아니오 → sessionStorage 플래그 (세션 내 재노출 금지) + PersistentCtaBanner 표시
예   → BudgetDraftFlow 오버레이
자동주문 알림(FR-106): plan 적용 상태 진입 시 1회 (localStorage promptHistory 기록)
```
- 접근성: BottomSheet 는 비모달(role="dialog", 포커스 이동하되 트랩은 열림 직후만), ESC/바깥 터치 닫기, 스크린리더 탐색 강탈 금지

## 5. 로그인 페이지 + 인증 흐름 (프론트 관점)

```
/login: 브랜드 영역 + SocialLoginButtons (ko: 카카오→구글→[애플 P1] / en: 구글→[애플]→카카오 최하단)
버튼 → location.href = /api/v1/auth/{provider}/authorize?next={복귀경로}
복귀(?login=success) → GET /users/me →
  hasBudgetPlan=true → 홈
  false + 로컬 게스트 plan 있음 → importGuestPlan() → 성공: 온보딩 스킵 확인 화면 → 홈
  false + 없음 → /onboarding
?error={code} → i18n 배너 (거부/오류 구분, 재시도 버튼)
```

## 6. i18n 키 체계 (`messages/ko.json`, `en.json` — 동시 수정 필수)

```
{domain}.{화면/컴포넌트}.{요소}  — 예:
guestHome.trialBadge.label / guestHome.prompt.title / guestHome.prompt.accept / guestHome.prompt.decline
guestHome.cta.banner / guestHome.sampleLabel / guestHome.autoOrderPrompt.title
budgetDraft.step1.title ~ step3.*, budgetDraft.direction.{health|diet|hearty|kids}
auth.login.title / auth.login.{kakao|google|apple} / auth.error.{AUTH_PROVIDER_DENIED|AUTH_INVALID_STATE|AUTH_PROVIDER_ERROR}
auth.notice.AUTH_EMAIL_CONFLICT_NOTICE / auth.gate.title
common.money 포맷은 MoneyText 가 Intl.NumberFormat 으로 처리 (키 아님)
```
- API 에러 `detail.code` → `auth.error.{code}` 규약으로 자동 매핑, 미정의 코드는 `common.error.fallback`

## 7. 회원 홈 (member 모드) — v1.1 증보

**데이터 어댑터** (`features/mealplan/` — v1.1 문구 'store/order 디렉토리 생성 금지'는 **v1.7에서 해제**, `features/order/` 는 13장):
```
useMemberHome():
  GET /users/me → hasBudgetPlan=false → BudgetPlanGate (BudgetDraftFlow 재사용, POST /budget/plans source='onboarding')
  GET /mealplans/latest → 404 MEALPLAN_NOT_FOUND → EmptyPlanHero (예산 락 히어로 + "내 식단 만들기" CTA)
                        → 200 → mapPlanToViewModel(MealPlanResponse) → HomeShell (mode: 'member')
```
- `mapPlanToViewModel`: meals(planDate·mealType) → weekPlan, budgetSummary → budgetMood. **ViewModel 은 옵셔널 필드 확장만** (게스트 계약 불변): `selectedDate?`, `overBudget?`, `planId?`
- 컴포넌트 신규: `EmptyPlanHero`, `PlanCreateSheet`(기간 스테퍼 + 알레르기/선호 칩 입력 — 30자/10개 클라이언트 검증), `GenerationLoading`(단계 문구 로테이션 + 스켈레톤, aria-busy), `OverBudgetBanner`(재생성 유도), `LockedFeatureCard`(냉장고/자동주문 "준비 중")
- **v1.7**: 회원 자동주문 `LockedFeatureCard feature="order"` 는 **13장에서 해제** — `AutoOrderCard` 재사용(복제 금지). 식단 탭 프리미엄 잠금은 유지. 게스트 `guestHome.autoOrder` 문구 불변
- `POST /mealplans` 호출은 클라이언트 타임아웃 90초, 버튼 비활성으로 연타 방지. 429 → 대기 안내, 그 외 실패 → 재시도 배너
- 탭바: 회원도 fridge/cart 는 "준비 중" 안내(가입 게이트 아님), meal 탭은 식단 섹션 스크롤
- **v1.7**: 회원 장바구니 탭은 잠금 토스트 대신 `/orders` 이동 (13장). fridge 탭은 기존 `/fridge` 유지

**i18n 신규 키 체계**: `memberHome.empty.*`, `memberHome.create.*`(시트), `memberHome.loading.step1~3`, `memberHome.overBudget.*`, `memberHome.locked.*`, `mealplan.mealType.{breakfast|lunch|dinner}` — ko/en 동시

## 8. 온보딩 3스텝 + 진입 순서 — v1.2 증보 (프로토타입 1:1)

**`features/household/` 신규** — OnboardingWizard(/onboarding 실화면):
- STEP1 MemberStep: MEMBER_TYPES 상수(adult_m 남색/adult_f 블루/teen 그린/child 앰버/toddler 오렌지, 기본나이 35/33/15/9/4, 나이범위), 1~5인 프리셋(PRESETS), 카드 리스트(나이 −/+·삭제), 구성원 추가, "N인 가구" 칩
- STEP2 BudgetStep: 슬라이더(min 80k·권장 130k·max 220k ×인원, USD 60/100/170), 대형 금액, 수준 배너(알뜰<권장≤적정<권장×1.3<여유), 예산 락 토글. 게스트 이전값 프리필
- STEP3 PreferenceStep: 음식 카드 6종 복수(korean/western/japanese/chinese/comfort/salad — 라벨 한식/양식/일식/중식/분식/샐러드·채식) + 방향 4종 단일 → "이 조건으로 식단 짜기"
- 완료: PUT households/me → PUT budget/plans → POST /mealplans(preferences=선호 라벨) → GenerationLoading 재사용 → 홈
- 각 스텝 [이전/다음], 프로토타입 마크업(지란고비.dc.html onboardStep) 기준 스타일

**진입 순서 규칙 (1장 갱신)**:
- 유효 세션: 회원 홈. 온보딩 미완료 → 샘플 홈 + "설정 마치고 식단 만들기" 배너(→/onboarding). 식단 없음(온보딩 완료) → 샘플 홈 + "내 식단 만들기" 배너(생성 시트). EmptyPlanHero 전면 노출 제거
- 게스트: visited 마커(localStorage `jaringobe.visited`, 로그아웃 시 기록) 있으면 [로그인하기/구경하기] 바텀시트 1회/세션 → 구경하기=게스트. 신규는 기존 10초 프롬프트
- i18n: `onboarding.step1~3.*`, `memberType.*`, `cuisine.*`, `entry.revisit.*` ko/en 동시

**게스트 체험 통일 (v1.2.1)**: 게스트의 예산 체험도 OnboardingWizard(guest 모드) 사용 — 서버 호출 없음, 완료 시 로컬 저장(GuestPlan 확장: members/cuisines/locked 옵셔널). 가입 시 위저드 3스텝 전체 프리필. BudgetDraftFlow 는 미사용 보존.

## 9. 설정 페이지 (v1.3)

- 라우트 `/settings`(보호 라우트 — 미들웨어 PROTECTED_PATHS 추가), 홈 헤더 GB 아바타 → 진입, 상단 뒤로가기
- 섹션: ① 계정 카드(users/me 프로필 + "로그인됨" 배지 + 로그아웃 — 확인 후 POST /auth/logout → visited 마커 → `/`) ② 내 식생활 설정 3행(현재값 요약: N인 가구/방향·선호/₩예산 — GET households·budget 값) ③ 자동 주문 연동 스토어(KR 4종 브랜드 배지: 컬리 #5F0080/쿠팡 블루/SSG 레드/네이버 그린, 연동하기/해제 + 연동됨 시 서비스 계정 이메일)
- 편집: 항목 클릭 → 온보딩 스텝 컴포넌트 **단일 편집 모드**(초기값 주입, 저장 시 PUT households·budget) → 성공 시 "식단을 다시 만들까요?" 확인 시트 → 수락: 재생성(GenerationLoading) → 홈 / 거절: 설정 유지
- 연동 토글: 연동하기 → 확인 시트("1단계: 연동 표시만, 실제 계정 연결은 준비 중" 안내) → PUT connections. 해제 동일
- i18n: `settings.*`, `store.{kurly|coupang|ssg|naver}` ko/en 동시

## 10. 식사 완료 + 레시피 시트 (v1.4)
- MealCard: 우측 완료 버튼(미완료=brand 파랑 CTA/완료=연한 배지+체크, 재터치 해제) — 낙관적 갱신·실패 롤백·연타 방지. member 전용(게스트=기존 게이트)
- 행 본문 클릭 → RecipeSheet(BottomSheet 재사용): 끼니 배지+"AI 추천 레시피" 배지, 요리명, 메타 3칩(timeMinutes||기본 "약 20분" / difficulty||"쉬움" / N인분=household size), 재료 칩, steps 번호 리스트, 닫기. 게스트 샘플은 기본 조리법 3단계 고정 문구
- i18n: mealplan.completion.*, recipe.* ko/en

## 11. 하단 "마이" 탭 (v1.5)
- 하단 탭바: 홈/냉장고/장바구니/**마이** (식단 탭은 추후 프리미엄 구독 편입 예정이라 제외 — 홈의 주간 식단 표시는 유지). 설정 진입을 상단 GB 아바타 → 하단 마이 탭으로 이동, 상단 GB 는 브랜드 마크(비버튼)로만 남겨 중복 제거 (HomeShell onMyTabClick)
- **v1.7**: 회원 장바구니 탭 클릭 → `/orders` (잠금 토스트 제거). 게스트 장바구니 탭은 기존 가입 게이트 유지
- 마이 탭: 회원 → /settings, 게스트 → 가입 게이트. 홈 탭은 홈 화면 유지(대체 아님). 가구 구성원/식단 방향·선호/월 예산 편집은 설정 페이지(9장)에 그대로

## 12. 지역·통화 전환 + 글로벌 배지 (v1.6 — 글로벌-지역전환)

- **설정 "지역·통화" 행**(9장 설정 페이지에 신설 — 계정 카드 아래·식생활 설정 위): 현재 지역 표시(`한국 ₩` / `글로벌 $`) + 전환 토글. 전환 시 **확인 시트**("기존 예산안·식단은 기존 통화로 유지됩니다" 안내, FR-606) → `PUT /users/me/region {country}` → 성공 시 `GET /users/me` 재조회 → 통화·스토어 세트·배지 즉시 반영
- **글로벌 배지**(FR-605): `user.country !== 'KR'` 일 때 `Badge`(tone `neutral`) "글로벌" 노출 — **홈 헤더**(HomeShell 인사말 옆, `TrialModeBadge` 와 병렬 슬롯 L144) + **설정 지역 행**. 통화 표기는 `MoneyText` 가 currency 기준 자동(추가 작업 없음)
- **국가별 스토어 리스트**: `features/store/constants.ts` 의 `STORE_IDS`/`STORE_BRAND_COLORS` 를 country 별 세트로 분기(KR 4 / US 2). US 브랜드 — Walmart `#0071CE`(mono W), Instacart `#43B02A`(mono I). `StoreConnectionsCard` 는 현재 country 세트만 렌더(9장 ③ 재사용)
- **재사용**: `MoneyText`(currency 포맷)·`Badge`·store 토글 인프라·`useSettings`(user.currency). **신규**: 지역 토글 컴포넌트 + `putUserRegion(country)` API 클라이언트(`features/settings` 또는 `features/store` 인접)
- i18n(ko/en 동시): `settings.region.{section, korea, global, switchConfirm.{title,description,confirm}, noRetroNotice}`, `common.globalBadge`(또는 `guestHome.globalBadge`), `store.{walmart|instacart}.{name,mono}`

## 13. 자동주문 P0 — 회원 카드·리뷰 (v1.7 / 타 설계 문서 v1.6)

> 기획: `docs/기획/자동주문-장바구니.md`. **AutoOrderCard 복제 금지** — `features/home/AutoOrderCard` 를 홈 셸에 유지하고 member CTA/카피만 props 또는 `memberHome.autoOrder` 네임스페이스로 확장. 게스트 `guestHome.autoOrder` 문구·동작 변경 없음.

**데이터 흐름**
```
useMemberHome (또는 인접 훅) + features/order/:
  GET /stores/connections → 연동 0개 / 1개+
  GET /orders/preview     → needed 칩 (최대 N개, 초과 "+K"), 스켈레톤+aria-busy
HomeShell member 분기:
  LockedFeatureCard feature="order" 제거 → AutoOrderCard 재사용
  미연동: 비활성 톤 + CTA "스토어 연동하기" → /settings
  연동: 활성 + 추천 칩 + CTA "장바구니 보기" → /orders
하단 장바구니 탭(member): /orders 이동 (잠금 토스트 아님)
냉장고 LockedFeatureCard href="/fridge" 유지
```

**`/orders` 리뷰 페이지** (`app/[locale]/orders/page.tsx`, `features/order/`)
- 인증 필수. 미인증 → `/login?next=/orders`
- 식단 없음(404 MEALPLAN_NOT_FOUND) → 빈 상태 "먼저 식단을 만들어 주세요" + 홈 CTA
- needed 없음(전부 냉장고 충당) → covered 목록 + 확정 버튼 **비활성** + "살 재료가 없어요"
- needed 있음:
  - 섹션 A: 살 재료 (needed) — 매칭 상품명/추정가 또는 "시세 없음". 시맨틱 리스트
  - 섹션 B: 냉장고가 충당 (covered) — 수량 fromFridge
  - 추정 합계 (없으면 ₩0 / $0) + 고지 **"연동 표시 기준 시뮬레이션 (실결제 아님)"** / EN 동등 (`not a real charge`)
  - KR 추정 카피: 네이버 쇼핑(컬리) 검색 기준임을 명시 (연동 스토어가 쿠팡이어도 가짜 몰 가격 금지)
  - 재확정 경고 1줄: "이미 확정한 주문이 있으면 재고가 늘어납니다" (멱등 P1)
  - [장바구니 확정] **명시 탭만**. 홈 진입·preview 조회로 주문을 만들지 않음
- 확정 성공: 스냅샷 + 다음 제안일(확정+7일, 표시만) + "냉장고에 담겼어요". 배지 **"시뮬레이션 확정"** — 승인번호·카드 마스킹·paid 스탬프 **금지**
- 실패/429: 배너+재시도 (클라이언트 라인 재전송 없음 — body 는 `{store}` 만)
- 미연동 store: 에러 배너 + 설정 CTA
- 접근성: 고지 텍스트를 버튼 근처에 **일반 텍스트**로(색만으로 구분 금지). 확정 후 라이브 리전으로 다음 제안일 안내. 확정 버튼 연타 방지(비활성)

**정직성**: 모든 확정 성공 화면에 시뮬레이션 고지 유지. 가짜 결제 완료 영수증 금지.

**i18n** (`messages/ko.json` · `en.json` 동시). 신규 키만 추가 — 게스트 키 변경 금지:

```
memberHome.autoOrder.title
memberHome.autoOrder.connectCta          // 스토어 연동하기
memberHome.autoOrder.viewCartCta         // 장바구니 보기
memberHome.autoOrder.disconnectedHint
memberHome.autoOrder.recommendedLabel
memberHome.autoOrder.moreCount           // +K
orders.title
orders.needed.title / orders.covered.title
orders.emptyMealplan.title / orders.emptyMealplan.cta
orders.nothingToOrder
orders.noPrice
orders.estimateTotal
orders.estimateSource                    // 네이버 쇼핑(컬리) 검색 기준
orders.simulationNotice                  // 연동 표시 기준 시뮬레이션 (실결제 아님)
orders.confirmCta
orders.confirmedBadge                    // 시뮬레이션 확정
orders.nextSuggested
orders.fridgeInbound                     // 냉장고에 담겼어요
orders.reconfirmWarning                  // 재확정 시 재고 증가 안내
orders.error.{STORE_NOT_CONNECTED|NOTHING_TO_ORDER|MEALPLAN_NOT_FOUND|ORDER_NOT_FOUND|RATE_LIMITED}
```

- API 에러 `detail.code` → `orders.error.{code}`, 미정의는 `common.error.fallback`
- `guestHome.autoOrder.*` 키·카피 변경 없음. 게스트 카드 CTA 는 기존 로그인

**재사용**: `AutoOrderCard`, `MoneyText`, `Badge`, `HomeShell`, store connections 조회. **신규**: `features/order/` (리뷰·확정 컨트롤러, API 클라이언트), `/orders` 페이지. store-adapter 문서·쿠팡/월마트 검색 UI 없음.

## 변경 이력
- 2026-08-15: **v1.7** — 자동주문 P0: 회원 AutoOrderCard 해제, `/orders` 리뷰, 장바구니 탭→/orders, i18n `memberHome.autoOrder`+`orders.*`. 정직 시뮬레이션 카피. 게스트 불변. (타 설계 문서는 동일 범위를 **v1.6** 으로 표기 — 본 문서는 지역전환이 이미 v1.6을 사용)
> **문서 정합 안내(v1.8)**: 아래 14장은 `feature/auto-order-p0`(13장 `/orders`, 본 문서 v1.7) 와 `feature/app-webview-push`(12장 앱 웹뷰·알림 설정, v1.5) 가 main 에 머지된 상태를 전제한다. 두 브랜치가 각각 12장/13장을 사용했으므로 머지 시 장 번호 재배정이 필요하다(문서 에이전트 소관).

## 14. 주간 자동 사이클 (v1.8 — 루프완결-주간사이클)

> 기획: `docs/기획/루프완결-주간사이클.md` 6장. **13장(자동주문 P0)의 `/orders` 화면을 확장**하며 새 페이지를 만들지 않는다. 신규 라우트 없음 — 사이클은 홈·주문·냉장고·설정 4개 기존 화면에 얹힌다.

### 14-1. 라우트·컴포넌트 증분

| 위치 | 신규/변경 | 내용 |
|------|-----------|------|
| `/` (홈) | **신규 컴포넌트** | `features/cycle/CycleStatusCard` — 사이클 상태 카드 (FR-824). `AutoOrderCard` **위**에 배치하고 두 카드를 합치지 않는다(사이클=시간축, 자동주문=장바구니 — 관심사가 다르다) |
| `/orders` | **확장** | 13장의 리뷰 화면에 상태 4종 분기 추가 (`draft`/`awaiting_user`/`confirmed`/`failed`) |
| `/fridge` | **신규 컴포넌트** | `features/fridge/DeliveryConfirmSheet` — 배송 확인·보정 시트 |
| `/settings` | **신규 컴포넌트** | `features/cycle/CycleSettingsCard` — 주기·요일·자동확정·일시정지 (9장 설정 페이지에 섹션 추가) |
| `features/cycle/` | **신규 디렉토리** | `api.ts`(`getCycle`/`putCycleSettings`/`postCycleSkip`), `types.ts`, `useCycle.ts` |

```
frontend/src/features/cycle/
  CycleStatusCard.tsx        # 홈 상태 카드 (stage 분기)
  CycleSettingsCard.tsx      # 설정 섹션
  DormantReturnCard.tsx      # 휴면 복귀 1회 카드 (FR-818)
  useCycle.ts / api.ts / types.ts
frontend/src/features/fridge/DeliveryConfirmSheet.tsx
frontend/src/features/order/   # 13장 기존 — 상태 분기만 확장 (복제 금지)
```

### 14-2. 홈 사이클 상태 카드 — `stage` 단일 분기 (FR-824)

`GET /cycle` 의 **`stage` 값 하나로 분기**한다. 프론트가 주문·식단 상태를 조합해 단계를 추론하지 않는다(추론 로직이 서버와 어긋나면 사용자에게 거짓말을 하게 된다).

| `stage` | 카드 표시 | 주 CTA |
|---------|-----------|--------|
| `idle` | "다음 주 식단은 {nextRunAt} 에 준비할게요" | — |
| `generating` | 스켈레톤 + `aria-busy="true"` "다음 주 식단 준비 중" | — |
| `generated` | "다음 주 식단이 나왔어요" | 식단 섹션으로 스크롤 / 재생성 |
| `generate_failed` | "다음 주 식단을 만들지 못했어요" | **직접 만들기** (`PlanCreateSheet`) |
| `drafted` | "장바구니 승인 대기 · {autoConfirmAt 까지}" | **[승인하기]** (1탭, 주 CTA) · [보기] · [이번 주 건너뛰기] |
| `awaiting_user` | 차단 사유 배너 (`blockedReason` → i18n) | 사유별 해소 CTA (아래) |
| `confirmed` | "배송 대기 · {deliveryEta} 도착 예정" | 주문 스냅샷 보기 · [주문 취소] |
| `delivered` | "이번 주 진행 중 · {완료}/{전체} 완료" | 식단 섹션(완료 체크) |
| `nothing_to_order` | "이번 주는 냉장고로 충분해요" | 냉장고 보기 |
| `skipped_user` | "이번 주는 쉬어가요" | — |
| `skipped_dormant` | **휴면 복귀 카드** "이번 주 식단 만들까요?" — 그 사이클에 **1회만** | **[만들기]** · [닫기] |
| `deferred_quota` | "곧 준비할게요" — **실패로 표시하지 않는다** | — |
| `paused` | "자동 사이클이 꺼져 있어요" | 설정으로 |

`blockedReason` → 해소 CTA 매핑:

| 사유 | 문구(요지) | CTA |
|------|-----------|-----|
| `BUDGET_EXCEEDED` | "예산을 넘을 것 같아요" | 승인 / 품목 제외(P1) / 식단 재생성 |
| `UNMATCHED_RATIO` | "못 찾은 재료가 많아요" | 장바구니 확인 |
| `STORE_DISCONNECTED` | "스토어 연동이 풀렸어요" | 설정으로 |
| `AUTO_CONFIRM_OFF` | "승인을 기다리고 있어요" | 승인하기 |
| `US_NO_PRICE` | "가격 정보가 없어 직접 확인이 필요해요" | 장바구니 확인 |
| `MEALPLAN_OVER_BUDGET` | "예산을 넘는 식단이에요" | 식단 재생성 |

- **휴면 복귀 카드 닫기(FR-818)** 는 `localStorage` 에 `cycle.dormantDismissed:{cycleStart}` 로만 기록한다(서버 상태 아님). 사이클이 바뀌면 자연히 다시 노출된다. **밀린 알림을 소급 표시하지 않는다.**
- **자동확정 예정 시각은 반드시 텍스트로** 표기한다: "내일 09:00에 자동으로 확정돼요" (사용자 로컬 시각). 통제감의 핵심 장치다.
- 상태 전이는 `aria-live="polite"` 라이브 리전으로 스크린리더에 통지한다.

### 14-3. `/orders` 상태 분기 확장 (13장 확장)

> **`GET /orders/latest` 계약 확장(api-spec 10-4)에 대응하는 필수 변경.** v1.6 화면은 `status='confirmed'` 만 가정하고 있어 초안 상태에서 오동작한다.

| status | 화면 |
|--------|------|
| `draft` | 섹션 A 살 재료(needed) / 섹션 B 냉장고가 충당(covered) + 추정 합계 + **시뮬레이션 고지** + **자동확정 예정 시각 안내** + [승인하기] / [품목 편집](P1) / [이번 주 건너뛰기] |
| `awaiting_user` | 상단 **차단 사유 배너**(위 매핑) + 해소 CTA. 나머지는 draft 와 동일 |
| `confirmed` | 스냅샷 + 배송 예정일 + `autoConfirmed` 면 "자동으로 확정됐어요" 배지 + [주문 취소](취소 기간 내) |
| `cancelled` / `expired` | 사유 문구 + 다음 사이클 안내. 조작 CTA 없음 |
| `failed` | 사유 + [다시 시도] |

- **승인 결과는 응답을 그대로 그린다.** 초안 캐시로 확정 화면을 만들지 않는다 — 서버 재계산 결과가 초안과 다를 수 있다(api-spec 10-1). 다를 경우 "재료가 조금 바뀌었어요" 안내를 1줄 표시한다.
- 시뮬레이션 고지는 **색이 아니라 텍스트**로 표기한다(색 단독 구분 금지, 접근성). 승인/확정 CTA 근처에 항상 유지.
- 승인 버튼은 요청 중 비활성(연타 방지). `409 ORDER_ALREADY_CONFIRMED` 수신 시 에러가 아니라 **"이미 확정됐어요"** 로 표시하고 최신 상태를 재조회한다(멱등의 UX 표현).

### 14-4. `/fridge` 배송 확인 시트

등록 직후(`fridge_inbound` 알림 탭 또는 `stage=confirmed→delivered` 전이) 냉장고 상단에 시트를 띄운다.

```
"받으셨나요? 이 재료들을 담아둘게요"
  [맞아요]        → POST /orders/{id}/delivery { received: true }
  [수량 수정]      → 기존 PATCH /fridge/items/{id} 재사용
  [아직 안 왔어요] → POST /orders/{id}/delivery { received: false }  (롤백 + 도착 예정 +1일)
```

- 문구를 **"담았어요"가 아니라 "받으셨나요?"** 로 한다 — `delivery_eta` 는 추정치이고, 단정했다가 실제로 안 왔으면 신뢰가 깨진다.
- 3회 "아직" 이후(`deliveryState='unknown'`)에는 시트를 자동으로 띄우지 않고 "받으면 알려주세요" 배너로 낮춘다.
- 유통기한은 등록 시 비어 있다(`expiresAt=null`). 시트에서 입력하도록 유도하되 강제하지 않는다.
- 기존 임박 배너에 "임박 재료는 다음 식단에 먼저 쓰여요" 한 줄을 추가한다(FR-806 의 사용자 체감 지점).

### 14-5. `/settings` 자동 주문 섹션

```
[자동 주문]
  사이클             [활성 / 일시정지]            → PUT /cycle/settings { enabled }
  주기               ( ) 주 1회  ( ) 주 2회        → { frequency }   ※ US 는 "주 1회 권장" 보조 문구
  기준 요일           [일 월 화 수 목 금 토]        → { anchorWeekday }  (0=일요일)
  자동확정            [on / off]                   → { autoConfirm }
                     off 설명: "항상 내가 승인할게요"
  타임존              (표시 + 변경)                 → { timezone }
  스토어 연동          (기존 9장 카드)
```

- `autoConfirm` 토글 아래에 고정 고지: **"자동확정은 알림 도달 여부와 무관하게 동작합니다"** (기획 10장 신뢰성 — 푸시가 안 와도 확정된다는 사실을 숨기지 않는다).
- 요일 선택은 **0=일요일** 기준(JS `getDay()`). API 와 UI 가 같은 규약을 쓴다.
- `frequency='biweekly'` 선택 시 "그레이스가 12시간으로 짧아져요" 안내 1줄.

### 14-6. i18n (`messages/ko.json` · `en.json` **동시 작성** — 하드코딩 금지)

신규 네임스페이스 `cycle.*` + 기존 `orders.*` 확장. **게스트 키(`guestHome.*`)는 변경하지 않는다.**

```
cycle.card.title
cycle.stage.{idle|generating|generated|generateFailed|drafted|awaitingUser|confirmed|delivered
             |nothingToOrder|skippedUser|skippedDormant|deferredQuota|paused}.{title,body}
cycle.stage.drafted.autoConfirmAt            // "{time}에 자동으로 확정돼요"
cycle.blocked.{BUDGET_EXCEEDED|UNMATCHED_RATIO|STORE_DISCONNECTED|AUTO_CONFIRM_OFF
               |US_NO_PRICE|MEALPLAN_OVER_BUDGET}.{title,cta}
cycle.cta.{approve|view|skip|createNow|dismiss|goSettings|cancelOrder}
cycle.dormant.{title,body,cta}
cycle.settings.{section,enabled,frequency,frequencyWeekly,frequencyBiweekly,frequencyUsHint,
                biweeklyGraceHint,anchorWeekday,autoConfirm,autoConfirmOffHint,
                autoConfirmPushNotice,timezone}
cycle.weekday.{0..6}
cycle.error.{CYCLE_ALREADY_CONFIRMED|RATE_LIMITED}

orders.status.{draft|awaitingUser|confirmed|cancelled|expired|failed}
orders.autoConfirmedBadge                    // "자동으로 확정됐어요"
orders.recalculatedNotice                    // "재료가 조금 바뀌었어요"
orders.alreadyConfirmed                      // 409 멱등 안내
orders.deliveryEta                           // "{date} 도착 예정"
orders.cancelCta
orders.error.{ORDER_INVALID_STATE|ORDER_ALREADY_CONFIRMED|ORDER_CANCEL_WINDOW_CLOSED}

fridge.delivery.{title,body,yes,adjust,notYet,unknownBanner}
fridge.expiring.nextPlanHint                 // "임박 재료는 다음 식단에 먼저 쓰여요"

notification.orderApproval.{title,body}
notification.fridgeInbound.{title,body}
notification.cyclePaused.{title,body}
settings.notifications.type.{orderApproval|fridgeInbound|cyclePaused}
```

- API 에러 `detail.code` → `cycle.error.{code}` / `orders.error.{code}`, 미정의는 `common.error.fallback`.
- 푸시 본문 템플릿의 **원본은 백엔드 `sender.TEMPLATES`**(api-spec 11-1)다. 위 `notification.*` 키는 **설정 화면의 타입 라벨·인앱 배너용**이며 푸시 본문을 프론트가 다시 만들지 않는다(이중 관리 금지).
- 날짜·시각·금액은 기존 `MoneyText`/`Intl` 포맷 재사용 — 로캘·통화(KRW/USD) 표시는 프론트 담당.

### 14-7. 접근성·상태 관리 원칙

- **파생 상태를 프론트에서 만들지 않는다**: `stage`·`blockedReason` 은 서버가 준 값을 그대로 분기한다. 클라이언트 추론은 서버와 어긋나는 순간 거짓 정보가 된다.
- 색 단독 구분 금지 — 시뮬레이션 고지, 차단 사유, 상태 배지는 전부 **텍스트**를 동반한다.
- 사이클 상태 전이·확정 결과는 `aria-live="polite"`. 생성 중 스켈레톤은 `aria-busy`.
- 폴링: `stage='generating'` 일 때만 `GET /mealplans/{id}` 폴링(기존 v1.5 규약 재사용). 그 외 상태에서 `/cycle` 자동 폴링을 하지 않는다 — 화면 진입·포커스 복귀 시 1회 조회로 충분하다(불필요한 서버 부하 방지).
- **푸시는 보조 채널**: 알림이 오지 않아도 홈 카드와 `/orders` 에서 동일한 정보·조작이 가능해야 한다. 푸시 전용 흐름을 만들지 않는다.

## 변경 이력
- 2026-08-30: **v1.8** — 주간 자동 사이클 14장: 홈 `CycleStatusCard`(stage 단일 분기 13종), `/orders` 상태 6종 확장(**latest 계약 확장 대응 필수**), `/fridge` 배송 확인 시트("받으셨나요?"), `/settings` 자동 주문 섹션, i18n `cycle.*` 신규 + `orders.*`/`fridge.delivery.*` 확장. 파생 상태 클라이언트 추론 금지 원칙. 신규 라우트 없음
- 2026-07-10: v1.6 — 지역·통화 전환 행 + 글로벌 배지 + 국가별 스토어 세트 12장 증보 (글로벌-지역전환)
- 2026-07-09: 최초 작성 (설계 토론 3라운드 UI 교차 검토 반영, 합의 완료)
- 2026-07-09: v1.1 — 회원 홈(member 모드) 7장 증보 (회원홈-식단연결 기획)
- 2026-07-09: v1.2 — 온보딩 3스텝(프로토타입 1:1)·진입 순서 8장 증보
- 2026-07-09: v1.2.1 — 게스트 체험을 동일 위저드(guest 모드)로 통일
- 2026-07-10: v1.3 — 설정 페이지 9장 (계정/식생활 편집·재생성/스토어 연동 상태)
