/**
 * API 응답/요청 타입 — docs/설계/api-spec.md 와 1:1 일치 (camelCase).
 */

/** 금액 — amount 는 Decimal 직렬화 문자열, float 금지 (api-spec 0장) */
export interface Money {
  amount: string;
  currency: 'KRW' | 'USD';
}

/** GET /api/v1/users/me — 200 UserMeResponse (api-spec 1-5) */
export interface UserMeResponse {
  id: string;
  nickname: string;
  email: string | null;
  profileImageUrl: string | null;
  locale: string;
  country: string;
  currency: string;
  onboardingCompleted: boolean;
  hasBudgetPlan: boolean;
}

/** 지원 지역(국가) — KR/US (api-spec 1-6, FR-602) */
export type Country = 'KR' | 'US';

/** PUT /api/v1/users/me/region 요청 (api-spec 1-6) — currency 는 서버가 매핑 */
export interface UserRegionUpdateRequest {
  country: Country;
}

export type MealDirection = 'health' | 'diet' | 'hearty' | 'kids';

/** POST /api/v1/budget/plans 요청 (api-spec 2-1) */
export interface BudgetPlanCreateRequest {
  householdSize: number;
  budget: Money;
  mealDirection: MealDirection;
  source: 'guest' | 'onboarding';
}

/** POST /api/v1/budget/plans — 201 BudgetPlanResponse */
export interface BudgetPlanResponse {
  id: string;
  householdSize: number;
  budget: Money;
  mealDirection: MealDirection;
  source: 'guest' | 'onboarding';
  createdAt: string;
}

/** 에러 공통 구조 (api-spec 0장) */
export interface ApiErrorDetail {
  code: string;
  message: string;
}
