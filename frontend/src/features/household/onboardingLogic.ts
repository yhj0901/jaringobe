import { HOUSEHOLD_MAX } from '@/shared/config/constants';
import {
  BUDGET_MOOD_RATIO,
  BUDGET_PER_PERSON,
  BUDGET_SLIDER_STEP,
  HOUSEHOLD_PRESETS,
  MEMBER_TYPES,
  type PresetSize,
} from '@/features/household/constants';
import type { HouseholdMemberType } from '@/features/household/types';
import type { Money } from '@/shared/api/types';

/**
 * 온보딩 위저드 순수 로직 (FR-311/312) — 예산 슬라이더 계산·수준 판정·구성원 규칙.
 * 슬라이더 금액은 step 배수의 정수만 다루므로 number 로 계산하고, 전송 시 문자열로 변환한다.
 */

export interface WizardMember {
  id: number;
  type: HouseholdMemberType;
  age: number;
}

/** 예산 수준 (FR-312 — ≤권장: 알뜰 / ≤권장×1.3: 적정 / 그 외: 여유) */
export type BudgetMood = 'frugal' | 'moderate' | 'roomy';

/** 프리셋 인원수 → 구성원 목록 (기본 나이 적용, FR-311) */
export function buildPresetMembers(size: PresetSize, startId = 1): WizardMember[] {
  return HOUSEHOLD_PRESETS[size].map((type, index) => ({
    id: startId + index,
    type,
    age: MEMBER_TYPES[type].defaultAge,
  }));
}

/** 구성원 수 기반 슬라이더 범위 (FR-312 — min/권장/max × 인원) */
export function budgetRange(size: number, currency: Money['currency']) {
  const perPerson = BUDGET_PER_PERSON[currency];
  return {
    min: perPerson.min * size,
    rec: perPerson.rec * size,
    max: perPerson.max * size,
    step: BUDGET_SLIDER_STEP[currency],
  };
}

/** 슬라이더 범위로 클램프 + step 배수 반올림 */
export function clampBudget(value: number, size: number, currency: Money['currency']): number {
  const { min, max, step } = budgetRange(size, currency);
  const snapped = Math.round(value / step) * step;
  return Math.max(min, Math.min(max, snapped));
}

/** 예산 수준 판정 — 정수 연산만 사용 (권장×1.3 은 13/10 분수 비교, float 금지) */
export function budgetMood(value: number, size: number, currency: Money['currency']): BudgetMood {
  const { rec } = budgetRange(size, currency);
  if (value <= rec) return 'frugal';
  if (value * BUDGET_MOOD_RATIO.den <= rec * BUDGET_MOOD_RATIO.num) return 'moderate';
  return 'roomy';
}

/** 1인당 금액 (표시용 반올림 정수) */
export function perPersonAmount(value: number, size: number): number {
  return size > 0 ? Math.round(value / size) : value;
}

/** 나이 조절 가능 여부 — 유형별 범위 (FR-311, api-spec 4-1 과 동일) */
export function canChangeAge(member: WizardMember, delta: 1 | -1): boolean {
  const config = MEMBER_TYPES[member.type];
  const next = member.age + delta;
  return next >= config.minAge && next <= config.maxAge;
}

/** 구성원 추가 가능 여부 (api-spec 4-1: 1~10명) */
export function canAddMember(members: readonly WizardMember[]): boolean {
  return members.length < HOUSEHOLD_MAX;
}

/** 구성원 삭제 가능 여부 — 최소 1명 유지 */
export function canRemoveMember(members: readonly WizardMember[]): boolean {
  return members.length > 1;
}
