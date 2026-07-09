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

  it('확장 필드(members/cuisines/locked) 왕복 — 게스트 위저드 결과 전달 (FR-315)', () => {
    const extended = {
      ...PREFILL,
      members: [
        { memberType: 'adult_m' as const, age: 35 },
        { memberType: 'toddler' as const, age: 4 },
      ],
      cuisines: ['korean' as const, 'salad' as const],
      locked: false,
    };
    saveOnboardingPrefill(extended);
    expect(readOnboardingPrefill()).toEqual(extended);
  });

  it('확장 필드 형식 위반도 전체 폐기한다 — CWE-20', () => {
    const invalids = [
      // 유형 열거 위반
      JSON.stringify({ ...PREFILL, members: [{ memberType: 'alien', age: 5 }] }),
      // 유형-나이 범위 위반 (유아 0~6)
      JSON.stringify({ ...PREFILL, members: [{ memberType: 'toddler', age: 30 }] }),
      // 빈 배열 (1~10명)
      JSON.stringify({ ...PREFILL, members: [] }),
      // 10명 초과
      JSON.stringify({
        ...PREFILL,
        members: Array.from({ length: 11 }, () => ({ memberType: 'adult_m', age: 35 })),
      }),
      // cuisines 열거 위반
      JSON.stringify({ ...PREFILL, cuisines: ['korean', 'thai'] }),
      // locked 타입 위반
      JSON.stringify({ ...PREFILL, locked: 'yes' }),
    ];
    for (const raw of invalids) {
      window.sessionStorage.setItem(ONBOARDING_PREFILL_SESSION_KEY, raw);
      expect(readOnboardingPrefill()).toBeNull();
    }
  });
});
