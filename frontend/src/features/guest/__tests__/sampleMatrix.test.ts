import { describe, expect, it } from 'vitest';
import {
  BUDGET_BANDS,
  HOUSEHOLD_BANDS,
  MEAL_DIRECTIONS,
  getDefaultViewModel,
  getSampleViewModel,
  toBudgetBand,
  toHouseholdBand,
} from '@/features/guest/sampleMatrix';
import type { AppLocale } from '@/i18n/routing';

const LOCALES: AppLocale[] = ['ko', 'en'];
const AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;

describe('샘플 매트릭스 (FR-105)', () => {
  it('가구 구간 × 예산 구간 × 식단 방향 × 로캘 전 조합이 조회된다 (스모크)', () => {
    for (const locale of LOCALES) {
      for (const householdBand of HOUSEHOLD_BANDS) {
        for (const budgetBand of BUDGET_BANDS) {
          for (const direction of MEAL_DIRECTIONS) {
            const vm = getSampleViewModel(
              locale,
              { householdBand, budgetBand, direction },
              'guest-planned',
            );
            // 주간 7일 × 아침/점심/저녁
            expect(vm.weekPlan).toHaveLength(7);
            for (const day of vm.weekPlan) {
              expect(day.meals).toHaveLength(3);
              for (const meal of day.meals) {
                expect(meal.name.length).toBeGreaterThan(0);
                expect(meal.isSample).toBe(true);
              }
            }
            // 예산 무드 — 문자열 금액 + 로캘 통화
            const expectedCurrency = locale === 'ko' ? 'KRW' : 'USD';
            for (const money of [
              vm.budgetMood.remaining,
              vm.budgetMood.saved,
              vm.budgetMood.wastePrevented,
            ]) {
              expect(money.amount).toMatch(AMOUNT_PATTERN);
              expect(money.currency).toBe(expectedCurrency);
            }
            // 냉장고 프리뷰 5개 내외 + 주문 추천
            expect(vm.fridgePreview.length).toBeGreaterThanOrEqual(3);
            expect(vm.fridgePreview.length).toBeLessThanOrEqual(7);
            expect(vm.autoOrder.recommendedItems?.length).toBeGreaterThan(0);
            expect(vm.autoOrder.stores.length).toBeGreaterThan(0);
          }
        }
      }
    }
  });

  it('guest-planned 모드에서 자동주문 카드가 활성화된다 (FR-106)', () => {
    const vm = getSampleViewModel(
      'ko',
      { householdBand: '2', budgetBand: 'p2', direction: 'diet' },
      'guest-planned',
    );
    expect(vm.autoOrder.active).toBe(true);
  });

  it('기본 ViewModel 은 guest-default 모드 + 비활성 자동주문이다', () => {
    for (const locale of LOCALES) {
      const vm = getDefaultViewModel(locale);
      expect(vm.mode).toBe('guest-default');
      expect(vm.autoOrder.active).toBe(false);
      expect(vm.weekPlan).toHaveLength(7);
    }
  });
});

describe('toHouseholdBand', () => {
  it('가구 인원을 1/2/3-4/5+ 구간으로 매핑한다', () => {
    expect(toHouseholdBand(1)).toBe('1');
    expect(toHouseholdBand(2)).toBe('2');
    expect(toHouseholdBand(3)).toBe('3-4');
    expect(toHouseholdBand(4)).toBe('3-4');
    expect(toHouseholdBand(5)).toBe('5plus');
    expect(toHouseholdBand(10)).toBe('5plus');
  });
});

describe('toBudgetBand', () => {
  it('ko 프리셋 금액은 자기 구간으로 매핑된다', () => {
    expect(toBudgetBand('300000', 'ko')).toBe('p1');
    expect(toBudgetBand('500000', 'ko')).toBe('p2');
    expect(toBudgetBand('700000', 'ko')).toBe('p3');
    expect(toBudgetBand('1000000', 'ko')).toBe('p4');
  });

  it('직접 입력 금액은 가장 가까운 구간으로 매핑된다 (정수 비교)', () => {
    expect(toBudgetBand('50000', 'ko')).toBe('p1');
    expect(toBudgetBand('399999', 'ko')).toBe('p1');
    expect(toBudgetBand('400000', 'ko')).toBe('p2');
    expect(toBudgetBand('849999', 'ko')).toBe('p3');
    expect(toBudgetBand('850000', 'ko')).toBe('p4');
    expect(toBudgetBand('5000000', 'ko')).toBe('p4');
  });

  it('en(USD) 구간도 동일 규칙으로 매핑된다', () => {
    expect(toBudgetBand('300', 'en')).toBe('p1');
    expect(toBudgetBand('450', 'en')).toBe('p2');
    expect(toBudgetBand('700', 'en')).toBe('p3');
    expect(toBudgetBand('2000', 'en')).toBe('p4');
  });
});
