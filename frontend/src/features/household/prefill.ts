import {
  HOUSEHOLD_MAX,
  HOUSEHOLD_MIN,
  ONBOARDING_PREFILL_SESSION_KEY,
} from '@/shared/config/constants';
import { CUISINE_IDS, MEMBER_TYPES } from '@/features/household/constants';
import { MEAL_DIRECTIONS } from '@/features/guest/sampleMatrix';
import type { GuestPlan } from '@/features/guest/store';
import type {
  Cuisine,
  HouseholdMemberInput,
  HouseholdMemberType,
} from '@/features/household/types';

/**
 * 게스트 예산안 이전 직후 온보딩 프리필 (FR-315) — sessionStorage 전달.
 * 이전 성공 시 PostLoginHandler 가 저장하고, 위저드가 STEP1 구성원·STEP2 예산·STEP3 선호에 프리필한다.
 * 게스트 3스텝 위저드 확장분(members/cuisines/locked)도 함께 전달된다.
 * PII/토큰 아님 (인원·나이·금액·통화·선호만, CWE-922 준수).
 */

export type OnboardingPrefill = GuestPlan;

export function saveOnboardingPrefill(prefill: OnboardingPrefill): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(ONBOARDING_PREFILL_SESSION_KEY, JSON.stringify(prefill));
}

function isValidMember(value: unknown): value is HouseholdMemberInput {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<HouseholdMemberInput>;
  if (typeof candidate.memberType !== 'string' || !(candidate.memberType in MEMBER_TYPES)) {
    return false;
  }
  const config = MEMBER_TYPES[candidate.memberType as HouseholdMemberType];
  return (
    typeof candidate.age === 'number' &&
    Number.isInteger(candidate.age) &&
    candidate.age >= config.minAge &&
    candidate.age <= config.maxAge
  );
}

function isValidMembers(value: unknown): value is HouseholdMemberInput[] {
  return (
    Array.isArray(value) &&
    value.length >= HOUSEHOLD_MIN &&
    value.length <= HOUSEHOLD_MAX &&
    value.every(isValidMember)
  );
}

function isValidCuisines(value: unknown): value is Cuisine[] {
  return (
    Array.isArray(value) &&
    value.length <= CUISINE_IDS.length &&
    value.every((item) => (CUISINE_IDS as readonly string[]).includes(item as string))
  );
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
    // 옵셔널 확장 필드 — 존재하면 형식 검증, 위반 시 전체 폐기 (변조 의심)
    const membersValid = candidate.members === undefined || isValidMembers(candidate.members);
    const cuisinesValid = candidate.cuisines === undefined || isValidCuisines(candidate.cuisines);
    const lockedValid = candidate.locked === undefined || typeof candidate.locked === 'boolean';
    if (
      !sizeValid ||
      !amountValid ||
      !currencyValid ||
      !directionValid ||
      !membersValid ||
      !cuisinesValid ||
      !lockedValid
    ) {
      return null;
    }
    return {
      householdSize: candidate.householdSize as number,
      amount: candidate.amount as string,
      currency: candidate.currency as OnboardingPrefill['currency'],
      mealDirection: candidate.mealDirection as OnboardingPrefill['mealDirection'],
      ...(candidate.members !== undefined ? { members: candidate.members } : {}),
      ...(candidate.cuisines !== undefined ? { cuisines: candidate.cuisines } : {}),
      ...(candidate.locked !== undefined ? { locked: candidate.locked } : {}),
    };
  } catch {
    return null;
  }
}

export function clearOnboardingPrefill(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(ONBOARDING_PREFILL_SESSION_KEY);
}
