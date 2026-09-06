import type { Money } from '@/shared/api/types';

/**
 * mealplan 도메인 API 타입 — docs/설계/api-spec.md 3장(v1.5)과 1:1 일치 (camelCase).
 */

/** v1.5 비동기 전환 — processing/failed 확장 (api-spec 3-2) */
export type MealPlanStatus = 'processing' | 'ready' | 'over_budget' | 'failed';

/** 조리 난이도 (MealOut.difficulty, api-spec 3-4 v1.4) */
export type MealDifficulty = 'easy' | 'normal' | 'hard';

/** 식단 재료 (MealPlanResponse.meals[].ingredients[]) */
export interface MealPlanIngredient {
  id: string;
  name: string;
  quantity: string;
  unit: string;
  estCost: Money;
}

/**
 * 끼니 (MealPlanResponse.meals[]) — mealType 은 서버 열거값 (breakfast|lunch|dinner).
 * v1.4 MealOut 확장(하위 호환 옵셔널): steps·completedAt·timeMinutes·difficulty (api-spec 3-4).
 */
export interface MealPlanMeal {
  id: string;
  planDate: string;
  mealType: string;
  recipeName: string;
  ingredients: MealPlanIngredient[];
  /** 조리 단계 (신규 생성분부터 LLM 이 채움) */
  steps?: string[];
  /** 완료 시각 — 완료=ISO datetime, 미완료=null (FR-501) */
  completedAt?: string | null;
  /** 조리 시간(분) — 부재 시 프론트 기본값 */
  timeMinutes?: number | null;
  /** 조리 난이도 — 부재 시 프론트 기본값 */
  difficulty?: MealDifficulty | null;
}

/** PUT /mealplans/{planId}/meals/{mealId}/completion 요청 (api-spec 3-4, FR-501) */
export interface MealCompletionRequest {
  completed: boolean;
}

/** 예산 요약 (FR-206) */
export interface MealPlanBudgetSummary {
  budget: Money;
  plannedCost: Money;
  remaining: Money;
  withinBudget: boolean;
}

/**
 * GET /mealplans/latest · GET /mealplans/{id} — 200 MealPlanResponse (api-spec 3-1/3-3).
 * v1.5 status 별 규칙: processing/failed 는 meals=[], budgetSummary=null, periodStart/End=null.
 */
export interface MealPlanResponse {
  id: string;
  status: MealPlanStatus;
  region: string;
  currency: Money['currency'];
  periodStart: string | null;
  periodEnd: string | null;
  budgetSummary: MealPlanBudgetSummary | null;
  meals: MealPlanMeal[];
  notes: string[];
}

/** POST /mealplans · regenerate — 202 MealPlanAcceptedResponse (api-spec 3-2 v1.5) */
export interface MealPlanAcceptedResponse {
  id: string;
  status: MealPlanStatus;
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
