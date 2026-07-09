import type { UserMeResponse } from '@/shared/api/types';

/**
 * 로그인 복귀(?login=success) 후 분기 규칙 (ui-design 5장, FR-108)
 *
 * hasBudgetPlan=true            → 홈 유지
 * false + 로컬 게스트 plan 있음 → importGuestPlan() 시도
 * false + 없음                  → /onboarding
 */
export type PostLoginAction = 'stay' | 'import-guest-plan' | 'go-onboarding';

export function resolvePostLoginAction(
  me: Pick<UserMeResponse, 'hasBudgetPlan'>,
  hasGuestPlan: boolean,
): PostLoginAction {
  if (me.hasBudgetPlan) return 'stay';
  return hasGuestPlan ? 'import-guest-plan' : 'go-onboarding';
}
