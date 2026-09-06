import { describe, expect, it } from 'vitest';
import {
  BUDGET_BANDS,
  HOUSEHOLD_BANDS,
  MEAL_DIRECTIONS,
  getDefaultViewModel,
  getMatrix,
  getSampleViewModel,
  toBudgetBand,
  toHouseholdBand,
} from '@/features/guest/sampleMatrix';
import type { AppLocale } from '@/i18n/routing';

import { budgetRange } from '@/features/household/onboardingLogic';
import { BUDGET_PRESETS, HOUSEHOLD_MIN, HOUSEHOLD_MAX } from '@/shared/config/constants';

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


describe('입력 예산을 반영하는 체험 금액', () => {
  it.each(LOCALES)('%s: 모든 밴드의 샘플 금액은 기준 프리셋 이하다', (locale) => {
    const matrix = getMatrix(locale);
    for (const [index, band] of BUDGET_BANDS.entries()) {
      for (const household of HOUSEHOLD_BANDS) {
        for (const amount of Object.values(matrix.budgetMood[band][household])) {
          expect(BigInt(amount)).toBeLessThanOrEqual(BigInt(BUDGET_PRESETS[locale].amounts[index]!));
        }
      }
    }
  });

  it.each(LOCALES)('%s: 1~10인 위저드 최소·권장·최대 및 모든 슬라이더 값에서 예산을 넘지 않는다', (locale) => {
    const currency = BUDGET_PRESETS[locale].currency;
    for (let size = HOUSEHOLD_MIN; size <= HOUSEHOLD_MAX; size += 1) {
      const { min, rec, max, step } = budgetRange(size, currency);
      const amounts = new Set([min, rec, max]);
      for (let value = min; value <= max; value += step) amounts.add(value);
      for (const amount of amounts) {
        const vm = getSampleViewModel(locale, {
          householdBand: toHouseholdBand(size),
          budgetBand: toBudgetBand(String(amount), locale),
          direction: 'health',
        }, 'guest-planned', String(amount));
        for (const money of Object.values(vm.budgetMood)) {
          expect(BigInt(money.amount)).toBeGreaterThanOrEqual(0n);
          expect(BigInt(money.amount)).toBeLessThanOrEqual(BigInt(amount));
          expect(money.currency).toBe(currency);
        }
      }
    }
  });

  it.each([
    ['en', '120', '52', '16', '4'],
    ['ko', '130000', '57200', '17766', '5200'],
  ] as const)('%s: 보고된 저예산 잔액 초과를 재현하는 입력 %s', (locale, amount, remaining, saved, waste) => {
    const vm = getSampleViewModel(locale, {
      householdBand: '1', budgetBand: toBudgetBand(amount, locale), direction: 'diet',
    }, 'guest-planned', amount);
    expect(vm.budgetMood.remaining.amount).toBe(remaining);
    expect(vm.budgetMood.saved.amount).toBe(saved);
    expect(vm.budgetMood.wastePrevented.amount).toBe(waste);
  });

  it.each(LOCALES)('%s: 프리셋 입력은 기존 샘플 금액을 그대로 유지한다', (locale) => {
    for (const [index, band] of BUDGET_BANDS.entries()) {
      const selector = { householdBand: '1' as const, budgetBand: band, direction: 'health' as const };
      expect(getSampleViewModel(locale, selector, 'guest-planned', BUDGET_PRESETS[locale].amounts[index]).budgetMood)
        .toEqual(getSampleViewModel(locale, selector, 'guest-planned').budgetMood);
    }
  });
});
