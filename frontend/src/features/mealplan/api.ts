import { apiFetch, type ApiResult } from '@/shared/api/client';
import { MEALPLAN_CREATE_TIMEOUT_MS } from '@/features/mealplan/constants';
import type {
  MealPlanCreateRequest,
  MealPlanMeal,
  MealPlanRegenerateRequest,
  MealPlanResponse,
} from '@/features/mealplan/types';

/**
 * mealplan API 클라이언트 (api-spec 3장 v1.1) — 모든 호출은 shared/api/client 경유.
 */

/** GET /api/v1/mealplans/latest — 404 MEALPLAN_NOT_FOUND 는 빈 상태 분기 (api-spec 3-1) */
export function fetchLatestMealPlan(): Promise<ApiResult<MealPlanResponse>> {
  return apiFetch<MealPlanResponse>('/api/v1/mealplans/latest');
}

/** LLM 생성 계열 호출 공통 — 클라이언트 타임아웃 90초 (ui-design 7장) */
async function fetchWithGenerationTimeout(
  path: string,
  body: MealPlanCreateRequest | MealPlanRegenerateRequest,
): Promise<ApiResult<MealPlanResponse>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), MEALPLAN_CREATE_TIMEOUT_MS);
  try {
    return await apiFetch<MealPlanResponse>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

/** POST /api/v1/mealplans — 식단 생성 (api-spec 3-2, FR-203) */
export function createMealPlan(body: MealPlanCreateRequest): Promise<ApiResult<MealPlanResponse>> {
  return fetchWithGenerationTimeout('/api/v1/mealplans', body);
}

/** POST /api/v1/mealplans/{id}/regenerate — 전체 재생성 scope=all (api-spec 3-5, FR-209) */
export function regenerateMealPlan(planId: string): Promise<ApiResult<MealPlanResponse>> {
  return fetchWithGenerationTimeout(
    `/api/v1/mealplans/${encodeURIComponent(planId)}/regenerate`,
    { scope: 'all' },
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
