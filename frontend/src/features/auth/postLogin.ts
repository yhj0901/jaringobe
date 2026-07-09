import type { UserMeResponse } from '@/shared/api/types';

/**
 * 로그인 복귀(?login=success) 후 분기 규칙 (ui-design 5장·7장, FR-108/FR-207)
 *
 * hasBudgetPlan=true            → 홈 유지
 * false + 로컬 게스트 plan 있음 → importGuestPlan() 시도
 * false + 없음                  → 홈 유지 (member 홈의 BudgetPlanGate 가 예산안 작성 처리)
 */
export type PostLoginAction = 'stay' | 'import-guest-plan';

export function resolvePostLoginAction(
  me: Pick<UserMeResponse, 'hasBudgetPlan'>,
  hasGuestPlan: boolean,
): PostLoginAction {
  if (me.hasBudgetPlan) return 'stay';
  return hasGuestPlan ? 'import-guest-plan' : 'stay';
}
