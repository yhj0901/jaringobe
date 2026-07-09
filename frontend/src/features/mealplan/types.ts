import type { Money } from '@/shared/api/types';

/**
 * mealplan 도메인 API 타입 — docs/설계/api-spec.md 3장(v1.1)과 1:1 일치 (camelCase).
 */

export type MealPlanStatus = 'ready' | 'over_budget';

/** 식단 재료 (MealPlanResponse.meals[].ingredients[]) */
export interface MealPlanIngredient {
  id: string;
  name: string;
  quantity: string;
  unit: string;
  estCost: Money;
}

/** 끼니 (MealPlanResponse.meals[]) — mealType 은 서버 열거값 (breakfast|lunch|dinner) */
export interface MealPlanMeal {
  id: string;
  planDate: string;
  mealType: string;
  recipeName: string;
  ingredients: MealPlanIngredient[];
}

/** 예산 요약 (FR-206) */
export interface MealPlanBudgetSummary {
  budget: Money;
  plannedCost: Money;
  remaining: Money;
  withinBudget: boolean;
}

/** GET /mealplans/latest · POST /mealplans — 200/201 MealPlanResponse (api-spec 3-1/3-2) */
export interface MealPlanResponse {
  id: string;
  status: MealPlanStatus;
  region: string;
  currency: Money['currency'];
  periodStart: string;
  periodEnd: string;
  budgetSummary: MealPlanBudgetSummary;
  meals: MealPlanMeal[];
  notes: string[];
}

/** POST /mealplans 요청 (api-spec 3-2) — 팀원 스키마 준수, 임의 확장 금지 */
export interface MealPlanCreateRequest {
  days: number;
  mealsPerDay: number;
  allergies: string[];
  preferences: string[];
}

/** POST /mealplans/{id}/regenerate 요청 (api-spec 3-4) — 프론트는 scope=all 만 (P1) */
export interface MealPlanRegenerateRequest {
  scope: 'all' | 'meal';
  mealId?: string;
}
