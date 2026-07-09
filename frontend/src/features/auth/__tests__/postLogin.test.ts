import { describe, expect, it } from 'vitest';
import { resolvePostLoginAction } from '@/features/auth/postLogin';

describe('resolvePostLoginAction (ui-design 5장·8장, FR-108/FR-316)', () => {
  it('onboardingCompleted=true 이면 홈 유지', () => {
    expect(
      resolvePostLoginAction({ onboardingCompleted: true, hasBudgetPlan: true }, true),
    ).toBe('stay');
    expect(
      resolvePostLoginAction({ onboardingCompleted: true, hasBudgetPlan: true }, false),
    ).toBe('stay');
  });

  it('온보딩 미완료 + 예산안 없음 + 게스트 플랜 있음 → 이전 시도', () => {
    expect(
      resolvePostLoginAction({ onboardingCompleted: false, hasBudgetPlan: false }, true),
    ).toBe('import-guest-plan');
  });

  it('온보딩 미완료 + 게스트 플랜 없음 → /onboarding (FR-316)', () => {
    expect(
      resolvePostLoginAction({ onboardingCompleted: false, hasBudgetPlan: false }, false),
    ).toBe('onboarding');
  });

  it('온보딩 미완료 + 예산안 이미 보유 → 이전 없이 /onboarding (가구 설정만 남음)', () => {
    expect(
      resolvePostLoginAction({ onboardingCompleted: false, hasBudgetPlan: true }, true),
    ).toBe('onboarding');
  });
});
