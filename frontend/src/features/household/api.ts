import { apiFetch, type ApiResult } from '@/shared/api/client';
import type { BudgetPlanResponse } from '@/shared/api/types';
import type {
  BudgetPlanUpsertRequest,
  HouseholdMemberInput,
  HouseholdResponse,
} from '@/features/household/types';

/**
 * household·budget 확장 API 클라이언트 (api-spec 4장·5장 v1.2) — shared/api/client 경유.
 */

/** PUT /api/v1/households/me — 구성원 전체 교체 저장 (api-spec 4-1, FR-314) */
export function putHouseholdMembers(
  members: HouseholdMemberInput[],
): Promise<ApiResult<HouseholdResponse>> {
  return apiFetch<HouseholdResponse>('/api/v1/households/me', {
    method: 'PUT',
    body: JSON.stringify({ members }),
  });
}

/** PUT /api/v1/budget/plans — 온보딩·수정용 upsert (api-spec 5-1, FR-312/314) */
export function putBudgetPlan(
  body: BudgetPlanUpsertRequest,
): Promise<ApiResult<BudgetPlanResponse>> {
  return apiFetch<BudgetPlanResponse>('/api/v1/budget/plans', {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}
