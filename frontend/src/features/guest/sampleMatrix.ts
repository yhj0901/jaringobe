import koMatrix from '@/features/guest/sample-matrix/ko.json';
import enMatrix from '@/features/guest/sample-matrix/en.json';
import { BUDGET_PRESETS } from '@/shared/config/constants';
import type { MealDirection, Money } from '@/shared/api/types';
import type {
  DayPlan,
  FridgeItem,
  HomeViewModel,
  MealSlot,
  StoreBadge,
} from '@/features/home/types';
import type { AppLocale } from '@/i18n/routing';

/**
 * 정적 샘플 매트릭스 (FR-105) — 가구 구간 × 예산 구간 × 식단 방향 × 로캘.
 * 식단/냉장고는 방향별 대표 템플릿, 예산 무드는 (예산 구간 × 가구 구간) 셀 — 재사용 허용 규칙.
 */

export type HouseholdBand = '1' | '2' | '3-4' | '5plus';
export type BudgetBand = 'p1' | 'p2' | 'p3' | 'p4';

export const HOUSEHOLD_BANDS: readonly HouseholdBand[] = ['1', '2', '3-4', '5plus'];
export const BUDGET_BANDS: readonly BudgetBand[] = ['p1', 'p2', 'p3', 'p4'];
export const MEAL_DIRECTIONS: readonly MealDirection[] = ['health', 'diet', 'hearty', 'kids'];

interface MatrixMood {
  remaining: string;
  saved: string;
  wastePrevented: string;
}

interface MatrixDirectionCell {
  weekPlan: {
    day: string;
    meals: Record<MealSlot, string>;
  }[];
  fridgePreview: FridgeItem[];
  orderSuggestion: string[];
}

export interface SampleMatrix {
  version: number;
  currency: Money['currency'];
  default: { householdBand: HouseholdBand; budgetBand: BudgetBand; direction: MealDirection };
  stores: StoreBadge[];
  directions: Record<MealDirection, MatrixDirectionCell>;
  budgetMood: Record<BudgetBand, Record<HouseholdBand, MatrixMood>>;
}

const MATRICES: Record<AppLocale, SampleMatrix> = {
  ko: koMatrix as SampleMatrix,
  en: enMatrix as SampleMatrix,
};

export function getMatrix(locale: AppLocale): SampleMatrix {
  return MATRICES[locale];
}

/** 가구 인원 → 구간 (1 / 2 / 3-4 / 5+) */
export function toHouseholdBand(size: number): HouseholdBand {
  if (size <= 1) return '1';
  if (size === 2) return '2';
  if (size <= 4) return '3-4';
  return '5plus';
}

/**
 * 예산 금액(정수 문자열) → 가장 가까운 프리셋 구간.
 * 정수 비교만 사용 — float 연산 금지.
 */
export function toBudgetBand(amount: string, locale: AppLocale): BudgetBand {
  const presets = BUDGET_PRESETS[locale].amounts.map((a) => Number.parseInt(a, 10));
  const value = Number.parseInt(amount, 10);
  let bandIndex = presets.length - 1;
  for (let i = 0; i < presets.length - 1; i += 1) {
    const current = presets[i] ?? 0;
    const next = presets[i + 1] ?? 0;
    // 두 프리셋의 중간값(정수 내림) 미만이면 앞 구간
    const midpoint = Math.floor((current + next) / 2);
    if (value < midpoint) {
      bandIndex = i;
      break;
    }
  }
  return BUDGET_BANDS[bandIndex] ?? 'p4';
}

export interface SampleSelector {
  householdBand: HouseholdBand;
  budgetBand: BudgetBand;
  direction: MealDirection;
}

const MEAL_SLOTS: readonly MealSlot[] = ['breakfast', 'lunch', 'dinner'];

/** 매트릭스 셀 조회 → HomeViewModel (모든 조합이 조회 가능해야 한다) */
export function getSampleViewModel(
  locale: AppLocale,
  selector: SampleSelector,
  mode: HomeViewModel['mode'],
): HomeViewModel {
  const matrix = getMatrix(locale);
  const directionCell = matrix.directions[selector.direction];
  const mood = matrix.budgetMood[selector.budgetBand][selector.householdBand];
  const currency = matrix.currency;

  const weekPlan: DayPlan[] = directionCell.weekPlan.map((day) => ({
    day: day.day,
    meals: MEAL_SLOTS.map((slot) => ({
      slot,
      name: day.meals[slot],
      isSample: true,
    })),
  }));

  return {
    mode,
    budgetMood: {
      remaining: { amount: mood.remaining, currency },
      saved: { amount: mood.saved, currency },
      wastePrevented: { amount: mood.wastePrevented, currency },
    },
    weekPlan,
    fridgePreview: directionCell.fridgePreview,
    autoOrder: {
      active: mode === 'guest-planned',
      stores: matrix.stores,
      recommendedItems: directionCell.orderSuggestion,
    },
  };
}

/** 기본 샘플(예산안 미작성 게스트) ViewModel */
export function getDefaultViewModel(locale: AppLocale): HomeViewModel {
  const matrix = getMatrix(locale);
  return getSampleViewModel(locale, matrix.default, 'guest-default');
}
