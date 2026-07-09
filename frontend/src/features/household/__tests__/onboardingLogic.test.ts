import { describe, expect, it } from 'vitest';
import {
  budgetMood,
  budgetRange,
  buildPresetMembers,
  canAddMember,
  canChangeAge,
  canRemoveMember,
  clampBudget,
  perPersonAmount,
  type WizardMember,
} from '@/features/household/onboardingLogic';
import { HOUSEHOLD_PRESETS, MEMBER_TYPES } from '@/features/household/constants';

describe('buildPresetMembers (FR-311)', () => {
  it('프리셋 유형 순서·기본 나이(35/33/15/9/4)로 구성원을 만든다', () => {
    const members = buildPresetMembers(5);
    expect(members.map((m) => m.type)).toEqual([...HOUSEHOLD_PRESETS[5]]);
    expect(members.map((m) => m.age)).toEqual([35, 33, 9, 9, 4]);
    expect(members.map((m) => m.id)).toEqual([1, 2, 3, 4, 5]);
  });

  it('1인 프리셋은 성인 남성 1명', () => {
    expect(buildPresetMembers(1)).toEqual([{ id: 1, type: 'adult_m', age: 35 }]);
  });
});

describe('budgetRange · clampBudget (FR-312)', () => {
  it('KRW: 인원 × (80,000/130,000/220,000), step 10,000', () => {
    expect(budgetRange(5, 'KRW')).toEqual({
      min: 400_000,
      rec: 650_000,
      max: 1_100_000,
      step: 10_000,
    });
  });

  it('USD: 인원 × (60/100/170), step 10', () => {
    expect(budgetRange(2, 'USD')).toEqual({ min: 120, rec: 200, max: 340, step: 10 });
  });

  it('범위 밖 값은 min/max 로 클램프한다', () => {
    expect(clampBudget(100_000, 2, 'KRW')).toBe(160_000);
    expect(clampBudget(9_999_999, 2, 'KRW')).toBe(440_000);
  });

  it('step 배수로 반올림한다', () => {
    expect(clampBudget(265_001, 2, 'KRW')).toBe(270_000);
    expect(clampBudget(264_999, 2, 'KRW')).toBe(260_000);
    expect(clampBudget(207, 2, 'USD')).toBe(210);
  });
});

describe('budgetMood — 알뜰/적정/여유 3단계 (FR-312)', () => {
  it('권장 이하 → frugal(알뜰)', () => {
    expect(budgetMood(650_000, 5, 'KRW')).toBe('frugal');
    expect(budgetMood(400_000, 5, 'KRW')).toBe('frugal');
  });

  it('권장 초과 ~ 권장×1.3 이하 → moderate(적정)', () => {
    expect(budgetMood(660_000, 5, 'KRW')).toBe('moderate');
    // 650,000 × 1.3 = 845,000 (경계 포함)
    expect(budgetMood(845_000, 5, 'KRW')).toBe('moderate');
  });

  it('권장×1.3 초과 → roomy(여유)', () => {
    expect(budgetMood(850_000, 5, 'KRW')).toBe('roomy');
    expect(budgetMood(1_100_000, 5, 'KRW')).toBe('roomy');
  });

  it('USD 도 동일 규칙', () => {
    expect(budgetMood(100, 1, 'USD')).toBe('frugal');
    expect(budgetMood(130, 1, 'USD')).toBe('moderate');
    expect(budgetMood(140, 1, 'USD')).toBe('roomy');
  });
});

describe('perPersonAmount', () => {
  it('1인당 금액을 반올림 정수로 계산한다', () => {
    expect(perPersonAmount(650_000, 5)).toBe(130_000);
    expect(perPersonAmount(500_000, 3)).toBe(166_667);
    expect(perPersonAmount(100, 0)).toBe(100);
  });
});

describe('구성원 규칙 (FR-311, api-spec 4-1)', () => {
  const member = (type: WizardMember['type'], age: number): WizardMember => ({ id: 1, type, age });

  it('나이 스테퍼는 유형별 범위를 벗어나지 못한다', () => {
    expect(canChangeAge(member('toddler', 0), -1)).toBe(false);
    expect(canChangeAge(member('toddler', 6), 1)).toBe(false);
    expect(canChangeAge(member('toddler', 3), 1)).toBe(true);
    expect(canChangeAge(member('child', 7), -1)).toBe(false);
    expect(canChangeAge(member('teen', 19), 1)).toBe(false);
    expect(canChangeAge(member('adult_m', 99), 1)).toBe(false);
    expect(canChangeAge(member('adult_f', 20), -1)).toBe(false);
    expect(canChangeAge(member('adult_f', 20), 1)).toBe(true);
  });

  it('추가는 최대 10명, 삭제는 최소 1명 유지', () => {
    const one = [member('adult_m', MEMBER_TYPES.adult_m.defaultAge)];
    expect(canRemoveMember(one)).toBe(false);
    expect(canAddMember(one)).toBe(true);

    const ten = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      type: 'adult_m' as const,
      age: 35,
    }));
    expect(canAddMember(ten)).toBe(false);
    expect(canRemoveMember(ten)).toBe(true);
  });
});
