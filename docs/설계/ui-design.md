# UI 설계서 — 게스트 홈 + 로그인

> 대상 기획: `docs/기획/게스트홈-진입경험.md`, `docs/기획/로그인-소셜인증.md`
> 스택: Next.js 14+ App Router / TypeScript strict / Tailwind CSS / next-intl (ko/en)

## 1. 라우트 구조 (`src/app/[locale]/`)

| 라우트 | 렌더링 | 설명 |
|--------|--------|------|
| `/` | SSG 셸 + 클라이언트 게스트 로직 | 홈 — 게스트/회원 공용 셸. 회원 여부는 서버에서 쿠키로 판정해 데이터 소스 결정 |
| `/login` | RSC | 로그인 페이지. `?error={code}`·`?notice={code}` 를 i18n 매핑해 배너 표시 |
| `/onboarding` | RSC + 클라이언트 | 라우트 예약 (본 구현은 household 기획). 게스트 이전 성공 시 확인 화면 1장만 이번 범위 |
| 미들웨어 | - | 로캘 프리픽스(next-intl) + 보호 라우트(현 범위: `/onboarding`) 미인증 시 `/login?next=` 리다이렉트 |

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

**데이터 어댑터** (`features/mealplan/` 신규 — store/order 디렉토리 생성 금지):
```
useMemberHome():
  GET /users/me → hasBudgetPlan=false → BudgetPlanGate (BudgetDraftFlow 재사용, POST /budget/plans source='onboarding')
  GET /mealplans/latest → 404 MEALPLAN_NOT_FOUND → EmptyPlanHero (예산 락 히어로 + "내 식단 만들기" CTA)
                        → 200 → mapPlanToViewModel(MealPlanResponse) → HomeShell (mode: 'member')
```
- `mapPlanToViewModel`: meals(planDate·mealType) → weekPlan, budgetSummary → budgetMood. **ViewModel 은 옵셔널 필드 확장만** (게스트 계약 불변): `selectedDate?`, `overBudget?`, `planId?`
- 컴포넌트 신규: `EmptyPlanHero`, `PlanCreateSheet`(기간 스테퍼 + 알레르기/선호 칩 입력 — 30자/10개 클라이언트 검증), `GenerationLoading`(단계 문구 로테이션 + 스켈레톤, aria-busy), `OverBudgetBanner`(재생성 유도), `LockedFeatureCard`(냉장고/자동주문 "준비 중")
- `POST /mealplans` 호출은 클라이언트 타임아웃 90초, 버튼 비활성으로 연타 방지. 429 → 대기 안내, 그 외 실패 → 재시도 배너
- 탭바: 회원도 fridge/cart 는 "준비 중" 안내(가입 게이트 아님), meal 탭은 식단 섹션 스크롤

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

## 변경 이력
- 2026-07-09: 최초 작성 (설계 토론 3라운드 UI 교차 검토 반영, 합의 완료)
- 2026-07-09: v1.1 — 회원 홈(member 모드) 7장 증보 (회원홈-식단연결 기획)
- 2026-07-09: v1.2 — 온보딩 3스텝(프로토타입 1:1)·진입 순서 8장 증보
- 2026-07-09: v1.2.1 — 게스트 체험을 동일 위저드(guest 모드)로 통일
- 2026-07-10: v1.3 — 설정 페이지 9장 (계정/식생활 편집·재생성/스토어 연동 상태)
