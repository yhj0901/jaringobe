import type { MealDirection, Money } from '@/shared/api/types';

/**
 * household 도메인 API 타입 — docs/설계/api-spec.md 4장·5장(v1.2)과 1:1 일치 (camelCase).
 */

/** 구성원 유형 (api-spec 4-1 열거값) */
export type HouseholdMemberType = 'adult_m' | 'adult_f' | 'teen' | 'child' | 'toddler';

/** 선호 음식 종류 (api-spec 5-1 열거값) */
export type Cuisine = 'korean' | 'western' | 'japanese' | 'chinese' | 'comfort' | 'salad';

/** 구성원 1명 (요청/응답 공용) */
export interface HouseholdMemberInput {
  memberType: HouseholdMemberType;
  age: number;
}

/** PUT /api/v1/households/me 요청 — 전체 교체 저장 (api-spec 4-1) */
export interface HouseholdUpdateRequest {
  members: HouseholdMemberInput[];
}

/** PUT/GET /api/v1/households/me — 200 응답 (api-spec 4-1/4-2) */
export interface HouseholdResponse {
  members: HouseholdMemberInput[];
  size: number;
}

/** PUT /api/v1/budget/plans 요청 — 온보딩·수정용 upsert (api-spec 5-1) */
export interface BudgetPlanUpsertRequest {
  householdSize: number;
  budget: Money;
  mealDirection: MealDirection;
  locked: boolean;
  cuisines: Cuisine[];
}
