import { apiFetch, type ApiResult } from '@/shared/api/client';
import type {
  MealPlanAcceptedResponse,
  MealPlanCreateRequest,
  MealPlanMeal,
  MealPlanRegenerateRequest,
  MealPlanResponse,
} from '@/features/mealplan/types';

/**
 * mealplan API 클라이언트 (api-spec 3장 v1.5) — 모든 호출은 shared/api/client 경유.
 * 생성/재생성은 202 비동기 — 완료 확인은 GET /mealplans/{id} 폴링 (ui-design 12장).
 */

/** GET /api/v1/mealplans/latest — 404 MEALPLAN_NOT_FOUND 는 빈 상태 분기 (api-spec 3-1) */
export function fetchLatestMealPlan(): Promise<ApiResult<MealPlanResponse>> {
  return apiFetch<MealPlanResponse>('/api/v1/mealplans/latest');
}

/** GET /api/v1/mealplans/{id} — 생성 상태 폴링 겸용 (api-spec 3-3 v1.5, rate limit 미적용) */
export function fetchMealPlan(planId: string): Promise<ApiResult<MealPlanResponse>> {
  return apiFetch<MealPlanResponse>(`/api/v1/mealplans/${encodeURIComponent(planId)}`);
}

/** POST /api/v1/mealplans — 202 Accepted 비동기 생성 (api-spec 3-2 v1.5, FR-203/005) */
export function createMealPlan(
  body: MealPlanCreateRequest,
): Promise<ApiResult<MealPlanAcceptedResponse>> {
  return apiFetch<MealPlanAcceptedResponse>('/api/v1/mealplans', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** POST /api/v1/mealplans/{id}/regenerate — scope=all, 202 (api-spec 3-5 v1.5, FR-209) */
export function regenerateMealPlan(planId: string): Promise<ApiResult<MealPlanAcceptedResponse>> {
  const body: MealPlanRegenerateRequest = { scope: 'all' };
  return apiFetch<MealPlanAcceptedResponse>(
    `/api/v1/mealplans/${encodeURIComponent(planId)}/regenerate`,
    { method: 'POST', body: JSON.stringify(body) },
  );
}

/**
 * PUT /api/v1/mealplans/{planId}/meals/{mealId}/completion — 식사 완료 설정/해제 (api-spec 3-4, FR-501).
 * 200 갱신된 MealOut(단일 끼니) 반환. 본인 스코프(CWE-639)는 서버가 검증.
 */
export function setMealCompletion(
  planId: string,
  mealId: string,
  completed: boolean,
): Promise<ApiResult<MealPlanMeal>> {
  return apiFetch<MealPlanMeal>(
    `/api/v1/mealplans/${encodeURIComponent(planId)}/meals/${encodeURIComponent(mealId)}/completion`,
    { method: 'PUT', body: JSON.stringify({ completed }) },
  );
}
