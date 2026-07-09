import { apiFetch } from '@/shared/api/client';
import type { BudgetPlanCreateRequest, BudgetPlanResponse } from '@/shared/api/types';
import type { GuestPlan } from '@/features/guest/store';

/**
 * 홈 온보딩 예산안 생성 (FR-207) — POST /api/v1/budget/plans source='onboarding' (api-spec 2-1)
 * 예산안 없이 가입한 회원이 홈의 BudgetDraftFlow 재사용 흐름으로 서버에 저장한다.
 *
 * created        → 201: 생성 성공 (plan 에 확정 예산 포함 — 빈 상태 히어로 금액 표시)
 * already-exists → 409 BUDGET_PLAN_EXISTS: 경합 등으로 이미 보유 (호출측: 최신 식단 재조회)
 * invalid        → 422: 값 검증 실패
 * error          → 그 외 (네트워크/서버 오류)
 */
export type CreateOnboardingPlanResult =
  | { kind: 'created'; plan: BudgetPlanResponse }
  | { kind: 'already-exists' }
  | { kind: 'invalid' }
  | { kind: 'error' };

export async function createOnboardingPlan(plan: GuestPlan): Promise<CreateOnboardingPlanResult> {
  const body: BudgetPlanCreateRequest = {
    householdSize: plan.householdSize,
    budget: { amount: plan.amount, currency: plan.currency },
    mealDirection: plan.mealDirection,
    source: 'onboarding',
  };

  const result = await apiFetch<BudgetPlanResponse>('/api/v1/budget/plans', {
    method: 'POST',
    body: JSON.stringify(body),
  });

  if (result.ok) return { kind: 'created', plan: result.data };
  if (result.status === 409) return { kind: 'already-exists' };
  if (result.status === 422) return { kind: 'invalid' };
  return { kind: 'error' };
}
