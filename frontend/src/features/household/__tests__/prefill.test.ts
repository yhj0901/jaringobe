import { describe, expect, it } from 'vitest';
import {
  clearOnboardingPrefill,
  readOnboardingPrefill,
  saveOnboardingPrefill,
} from '@/features/household/prefill';
import { ONBOARDING_PREFILL_SESSION_KEY } from '@/shared/config/constants';

const PREFILL = {
  householdSize: 4,
  amount: '700000',
  currency: 'KRW' as const,
  mealDirection: 'kids' as const,
};

describe('온보딩 프리필 sessionStorage (FR-315)', () => {
  it('save → read 왕복', () => {
    saveOnboardingPrefill(PREFILL);
    expect(readOnboardingPrefill()).toEqual(PREFILL);
  });

  it('clear 후에는 null', () => {
    saveOnboardingPrefill(PREFILL);
    clearOnboardingPrefill();
    expect(readOnboardingPrefill()).toBeNull();
  });

  it('저장값이 없으면 null', () => {
    expect(readOnboardingPrefill()).toBeNull();
  });

  it('형식 위반(변조) 값은 null — CWE-20', () => {
    const invalids = [
      'not-json',
      JSON.stringify(null),
      JSON.stringify({ ...PREFILL, householdSize: 0 }),
      JSON.stringify({ ...PREFILL, householdSize: 11 }),
      JSON.stringify({ ...PREFILL, householdSize: 2.5 }),
      JSON.stringify({ ...PREFILL, amount: '70만원' }),
      JSON.stringify({ ...PREFILL, currency: 'EUR' }),
      JSON.stringify({ ...PREFILL, mealDirection: 'spicy' }),
    ];
    for (const raw of invalids) {
      window.sessionStorage.setItem(ONBOARDING_PREFILL_SESSION_KEY, raw);
      expect(readOnboardingPrefill()).toBeNull();
    }
  });
});
