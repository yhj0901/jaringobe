import { apiFetch } from '@/shared/api/client';
import type { BudgetPlanCreateRequest, BudgetPlanResponse } from '@/shared/api/types';
import type { GuestPlan } from '@/features/guest/store';

/**
 * 게스트 예산안 계정 이전 (FR-108) — POST /api/v1/budget/plans (api-spec 2-1)
 *
 * created        → 201: 이전 성공 (호출측: 로컬 삭제 + 온보딩 스킵 확인 화면)
 * already-exists → 409 BUDGET_PLAN_EXISTS: 기존 활성 예산안 보유 (호출측: 로컬 삭제만)
 * invalid        → 422: 변조 의심 — 게스트 값 폐기 후 일반 온보딩
 * error          → 그 외 (네트워크/서버 오류) — 로컬 데이터 유지
 */
export type ImportGuestPlanResult = 'created' | 'already-exists' | 'invalid' | 'error';

export async function importGuestPlan(plan: GuestPlan): Promise<ImportGuestPlanResult> {
  const body: BudgetPlanCreateRequest = {
    householdSize: plan.householdSize,
    budget: { amount: plan.amount, currency: plan.currency },
    mealDirection: plan.mealDirection,
    source: 'guest',
  };

  const result = await apiFetch<BudgetPlanResponse>('/api/v1/budget/plans', {
    method: 'POST',
    body: JSON.stringify(body),
  });

  if (result.ok) return 'created';
  if (result.status === 409) return 'already-exists';
  if (result.status === 422) return 'invalid';
  return 'error';
}
