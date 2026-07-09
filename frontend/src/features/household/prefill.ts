import { HOUSEHOLD_MAX, HOUSEHOLD_MIN, ONBOARDING_PREFILL_SESSION_KEY } from '@/shared/config/constants';
import { MEAL_DIRECTIONS } from '@/features/guest/sampleMatrix';
import type { GuestPlan } from '@/features/guest/store';

/**
 * 게스트 예산안 이전 직후 온보딩 프리필 (FR-315) — sessionStorage 전달.
 * 이전 성공 시 PostLoginHandler 가 저장하고, 위저드가 STEP1 프리셋·STEP2 예산·STEP3 방향에 프리필한다.
 * PII/토큰 아님 (인원·금액·통화·방향만, CWE-922 준수).
 */

export type OnboardingPrefill = GuestPlan;

export function saveOnboardingPrefill(prefill: OnboardingPrefill): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(ONBOARDING_PREFILL_SESSION_KEY, JSON.stringify(prefill));
}

/** 저장된 프리필 조회 — 형식 검증 실패 시 null (변조 값 불신, CWE-20) */
export function readOnboardingPrefill(): OnboardingPrefill | null {
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(ONBOARDING_PREFILL_SESSION_KEY);
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const candidate = parsed as Partial<OnboardingPrefill>;
    const sizeValid =
      typeof candidate.householdSize === 'number' &&
      Number.isInteger(candidate.householdSize) &&
      candidate.householdSize >= HOUSEHOLD_MIN &&
      candidate.householdSize <= HOUSEHOLD_MAX;
    const amountValid = typeof candidate.amount === 'string' && /^\d+$/.test(candidate.amount);
    const currencyValid = candidate.currency === 'KRW' || candidate.currency === 'USD';
    const directionValid =
      candidate.mealDirection !== undefined && MEAL_DIRECTIONS.includes(candidate.mealDirection);
    if (!sizeValid || !amountValid || !currencyValid || !directionValid) return null;
    return {
      householdSize: candidate.householdSize as number,
      amount: candidate.amount as string,
      currency: candidate.currency as OnboardingPrefill['currency'],
      mealDirection: candidate.mealDirection as OnboardingPrefill['mealDirection'],
    };
  } catch {
    return null;
  }
}

export function clearOnboardingPrefill(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(ONBOARDING_PREFILL_SESSION_KEY);
}
