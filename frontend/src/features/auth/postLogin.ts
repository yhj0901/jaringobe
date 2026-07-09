import type { UserMeResponse } from '@/shared/api/types';

/**
 * 로그인 복귀(?login=success) 후 분기 규칙 (ui-design 5장·8장, FR-108/FR-316)
 *
 * onboardingCompleted=true                    → 홈 유지
 * false + 예산안 없음 + 로컬 게스트 plan 있음 → importGuestPlan() 시도 후 /onboarding?imported=1
 * false + 그 외                               → /onboarding (실화면 위저드)
 */
export type PostLoginAction = 'stay' | 'import-guest-plan' | 'onboarding';

export function resolvePostLoginAction(
  me: Pick<UserMeResponse, 'onboardingCompleted' | 'hasBudgetPlan'>,
  hasGuestPlan: boolean,
): PostLoginAction {
  if (me.onboardingCompleted) return 'stay';
  if (!me.hasBudgetPlan && hasGuestPlan) return 'import-guest-plan';
  return 'onboarding';
}
