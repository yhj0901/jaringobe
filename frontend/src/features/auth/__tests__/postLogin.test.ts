import { describe, expect, it } from 'vitest';
import { resolvePostLoginAction } from '@/features/auth/postLogin';

describe('resolvePostLoginAction (ui-design 5장, FR-108)', () => {
  it('hasBudgetPlan=true 이면 홈 유지', () => {
    expect(resolvePostLoginAction({ hasBudgetPlan: true }, true)).toBe('stay');
    expect(resolvePostLoginAction({ hasBudgetPlan: true }, false)).toBe('stay');
  });

  it('hasBudgetPlan=false + 게스트 플랜 있음 → 이전 시도', () => {
    expect(resolvePostLoginAction({ hasBudgetPlan: false }, true)).toBe('import-guest-plan');
  });

  it('hasBudgetPlan=false + 게스트 플랜 없음 → 온보딩', () => {
    // FR-207: 예산안 없어도 홈 유지 — member 홈 BudgetPlanGate 가 처리
    expect(resolvePostLoginAction({ hasBudgetPlan: false }, false)).toBe('stay');
  });
});
