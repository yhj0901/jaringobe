import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  dayCodeOf,
  defaultSelectedDate,
  mapPlanToViewModel,
  sumIngredientCost,
  toLocalIsoDate,
} from '@/features/mealplan/mapPlanToViewModel';
import type { MealPlanIngredient, MealPlanResponse } from '@/features/mealplan/types';

function ingredient(name: string, amount: string): MealPlanIngredient {
  return {
    id: `ing-${name}`,
    name,
    quantity: '1',
    unit: 'ea',
    estCost: { amount, currency: 'KRW' },
  };
}

const PLAN: MealPlanResponse = {
  id: 'plan-1',
  status: 'ready',
  region: 'KR',
  currency: 'KRW',
  periodStart: '2026-07-08',
  periodEnd: '2026-07-09',
  budgetSummary: {
    budget: { amount: '700000.00', currency: 'KRW' },
    plannedCost: { amount: '612300.00', currency: 'KRW' },
    remaining: { amount: '87700.00', currency: 'KRW' },
    withinBudget: true,
  },
  meals: [
    // 의도적으로 날짜/끼니 순서를 섞어 정렬을 검증한다
    {
      id: 'm3',
      planDate: '2026-07-09',
      mealType: 'breakfast',
      recipeName: '계란볶음밥',
      ingredients: [ingredient('계란', '2000.00'), ingredient('밥', '1500.50')],
    },
    {
      id: 'm2',
      planDate: '2026-07-08',
      mealType: 'dinner',
      recipeName: '된장찌개',
      ingredients: [ingredient('두부', '1200.00')],
    },
    {
      id: 'm1',
      planDate: '2026-07-08',
      mealType: 'breakfast',
      recipeName: '토스트',
      ingredients: [],
    },
    {
      id: 'm4',
      planDate: '2026-07-08',
      mealType: 'lunch',
      recipeName: '비빔국수',
      ingredients: [ingredient('소면', '900')],
    },
  ],
  notes: [],
};

afterEach(() => {
  vi.useRealTimers();
});

describe('mapPlanToViewModel (FR-201)', () => {
  it('meals 를 planDate 오름차순 · 끼니(아침/점심/저녁) 순으로 weekPlan 에 매핑한다', () => {
    const vm = mapPlanToViewModel(PLAN, { selectedDate: '2026-07-08' });

    expect(vm.mode).toBe('member');
    expect(vm.planId).toBe('plan-1');
    expect(vm.weekPlan.map((d) => d.date)).toEqual(['2026-07-08', '2026-07-09']);
    expect(vm.weekPlan[0]?.day).toBe('wed');
    expect(vm.weekPlan[0]?.meals.map((m) => m.slot)).toEqual(['breakfast', 'lunch', 'dinner']);
    expect(vm.weekPlan[0]?.meals.map((m) => m.name)).toEqual(['토스트', '비빔국수', '된장찌개']);
    expect(vm.weekPlan.every((d) => d.meals.every((m) => !m.isSample))).toBe(true);
  });

  it('끼니 행에 재료명 목록과 추정 비용 합(Decimal 문자열 합산)을 담는다 (FR-205)', () => {
    const vm = mapPlanToViewModel(PLAN, { selectedDate: '2026-07-08' });
    const breakfast = vm.weekPlan[1]?.meals[0];

    expect(breakfast?.ingredients).toEqual(['계란', '밥']);
    expect(breakfast?.estCost).toEqual({ amount: '3500.50', currency: 'KRW' });
    // 재료 없는 끼니는 estCost 미표시
    expect(vm.weekPlan[0]?.meals[0]?.estCost).toBeUndefined();
    // 소수부 없는 금액("900")도 정상 합산
    expect(vm.weekPlan[0]?.meals[1]?.estCost).toEqual({ amount: '900.00', currency: 'KRW' });
  });

  it('budgetSummary → budgetMood 매핑 + withinBudget=false → overBudget (FR-206)', () => {
    const vm = mapPlanToViewModel(PLAN, { selectedDate: '2026-07-08' });
    expect(vm.overBudget).toBe(false);
    expect(vm.budgetMood.remaining).toEqual({ amount: '87700.00', currency: 'KRW' });
    expect(vm.budgetMood.wastePrevented).toEqual({ amount: '0', currency: 'KRW' });

    const overPlan: MealPlanResponse = {
      ...PLAN,
      status: 'over_budget',
      budgetSummary: {
        ...PLAN.budgetSummary,
        remaining: { amount: '-12300.00', currency: 'KRW' },
        withinBudget: false,
      },
    };
    const overVm = mapPlanToViewModel(overPlan, { selectedDate: '2026-07-08' });
    expect(overVm.overBudget).toBe(true);
    expect(overVm.budgetMood.remaining.amount).toBe('-12300.00');
  });

  it('회원 모드에선 냉장고/자동주문 셸 데이터를 비운다 (FR-208 잠금 카드 대체)', () => {
    const vm = mapPlanToViewModel(PLAN, { selectedDate: '2026-07-08' });
    expect(vm.fridgePreview).toEqual([]);
    expect(vm.autoOrder).toEqual({ active: false, stores: [] });
  });

  it('selectedDate 미지정 시 기본 선택 규칙(defaultSelectedDate)을 적용한다', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-09T10:00:00'));
    expect(mapPlanToViewModel(PLAN).selectedDate).toBe('2026-07-09');
  });
});

describe('defaultSelectedDate (FR-205: 오늘 기본)', () => {
  it('오늘이 기간 내면 오늘, 아니면 periodStart', () => {
    expect(defaultSelectedDate(PLAN, new Date('2026-07-09T01:00:00'))).toBe('2026-07-09');
    expect(defaultSelectedDate(PLAN, new Date('2026-08-01T01:00:00'))).toBe('2026-07-08');
    expect(defaultSelectedDate(PLAN, new Date('2026-07-01T01:00:00'))).toBe('2026-07-08');
  });
});

describe('sumIngredientCost / 날짜 유틸', () => {
  it('빈 재료 목록 → undefined', () => {
    expect(sumIngredientCost([])).toBeUndefined();
  });

  it('음수 금액도 문자열 파싱으로 합산한다 (float 금지)', () => {
    expect(sumIngredientCost([ingredient('a', '-500.25'), ingredient('b', '1000.00')])).toEqual({
      amount: '499.75',
      currency: 'KRW',
    });
    expect(sumIngredientCost([ingredient('a', '-500.25'), ingredient('b', '100.00')])).toEqual({
      amount: '-400.25',
      currency: 'KRW',
    });
  });

  it('dayCodeOf 는 UTC 기준 요일 코드를 돌려준다', () => {
    expect(dayCodeOf('2026-07-05')).toBe('sun');
    expect(dayCodeOf('2026-07-06')).toBe('mon');
    expect(dayCodeOf('2026-07-11')).toBe('sat');
  });

  it('toLocalIsoDate 는 로컬 달력 날짜를 YYYY-MM-DD 로 포맷한다', () => {
    expect(toLocalIsoDate(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});
