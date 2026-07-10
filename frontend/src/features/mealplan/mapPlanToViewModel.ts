import type { Money } from '@/shared/api/types';
import type { DayPlan, HomeViewModel, MealItem, MealSlot } from '@/features/home/types';
import type { MealPlanIngredient, MealPlanMeal, MealPlanResponse } from '@/features/mealplan/types';

/**
 * MealPlanResponse → HomeViewModel 매핑 (FR-201) — 홈 셸 주입 계약 불변, 옵셔널 필드 확장만.
 * meals(planDate·mealType) → weekPlan, budgetSummary → budgetMood.
 */

const DAY_CODES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const;

/** YYYY-MM-DD → 요일 코드 (mon..sun) — UTC 자정 기준 (달력 날짜라 타임존 무관) */
export function dayCodeOf(date: string): string {
  const utc = new Date(`${date}T00:00:00Z`);
  return DAY_CODES[utc.getUTCDay()] ?? 'mon';
}

/** 로컬 달력 기준 오늘 날짜 (YYYY-MM-DD) — 식단 일자는 사용자 달력 기준 */
export function toLocalIsoDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** 기본 선택 일자 — 오늘이 기간 내면 오늘, 아니면 periodStart (FR-205: 오늘 날짜 기본) */
export function defaultSelectedDate(
  plan: Pick<MealPlanResponse, 'periodStart' | 'periodEnd'>,
  today: Date = new Date(),
): string {
  const todayIso = toLocalIsoDate(today);
  if (todayIso >= plan.periodStart && todayIso <= plan.periodEnd) return todayIso;
  return plan.periodStart;
}

/** Decimal 문자열 → 센트 정수 (float 금지 — 문자열 파싱만 사용) */
function toCents(amount: string): number {
  const negative = amount.startsWith('-');
  const raw = negative ? amount.slice(1) : amount;
  const [intPart = '0', fracPart = ''] = raw.split('.');
  const frac = `${fracPart}00`.slice(0, 2);
  const value = Number.parseInt(intPart === '' ? '0' : intPart, 10) * 100 + Number.parseInt(frac, 10);
  return negative ? -value : value;
}

/** 센트 정수 → Decimal 문자열 (소수 2자리) */
function fromCents(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

/** 끼니 추정 비용 = 재료 estCost 합 (FR-205) — 재료가 없으면 undefined */
export function sumIngredientCost(ingredients: MealPlanIngredient[]): Money | undefined {
  const first = ingredients[0];
  if (first === undefined) return undefined;
  const cents = ingredients.reduce((acc, ingredient) => acc + toCents(ingredient.estCost.amount), 0);
  return { amount: fromCents(cents), currency: first.estCost.currency };
}

const MEAL_SLOT_ORDER: Record<MealSlot, number> = { breakfast: 0, lunch: 1, dinner: 2 };

function isKnownSlot(mealType: string): mealType is MealSlot {
  return mealType in MEAL_SLOT_ORDER;
}

function toMealItem(meal: MealPlanMeal & { mealType: MealSlot }): MealItem {
  return {
    slot: meal.mealType,
    name: meal.recipeName,
    isSample: false,
    ingredients: meal.ingredients.map((ingredient) => ingredient.name),
    estCost: sumIngredientCost(meal.ingredients),
    // v1.4 완료·레시피 확장 (FR-501/502/504) — 없는 필드는 undefined 로 남겨 시트가 기본값 처리
    mealId: meal.id,
    recipeIngredients: meal.ingredients.map((ingredient) => ({
      name: ingredient.name,
      quantity: ingredient.quantity,
      unit: ingredient.unit,
    })),
    steps: meal.steps,
    completedAt: meal.completedAt ?? null,
    timeMinutes: meal.timeMinutes ?? null,
    difficulty: meal.difficulty ?? null,
  };
}

export interface MapPlanOptions {
  /** 주간 스트립에서 선택된 일자 — 미지정 시 기본 선택 규칙 적용 */
  selectedDate?: string;
}

export function mapPlanToViewModel(
  plan: MealPlanResponse,
  options?: MapPlanOptions,
): HomeViewModel {
  const byDate = new Map<string, MealPlanMeal[]>();
  for (const meal of plan.meals) {
    const list = byDate.get(meal.planDate);
    if (list) list.push(meal);
    else byDate.set(meal.planDate, [meal]);
  }

  const weekPlan: DayPlan[] = [...byDate.keys()].sort().map((date) => ({
    day: dayCodeOf(date),
    date,
    meals: (byDate.get(date) ?? [])
      .filter((meal): meal is MealPlanMeal & { mealType: MealSlot } => isKnownSlot(meal.mealType))
      .sort((a, b) => MEAL_SLOT_ORDER[a.mealType] - MEAL_SLOT_ORDER[b.mealType])
      .map(toMealItem),
  }));

  return {
    mode: 'member',
    planId: plan.id,
    overBudget: !plan.budgetSummary.withinBudget,
    selectedDate: options?.selectedDate ?? defaultSelectedDate(plan),
    budgetMood: {
      remaining: plan.budgetSummary.remaining,
      // 회원 v0: 절약분 = 예산 - 편성 비용(= remaining). 폐기 절감은 냉장고 도입 전이라 0 (기획 Out of Scope)
      saved: plan.budgetSummary.remaining,
      wastePrevented: { amount: '0', currency: plan.currency },
    },
    weekPlan,
    // 냉장고/자동주문은 회원에게 "준비 중" 잠금 카드로 대체 (FR-208) — 셸 데이터는 비움
    fridgePreview: [],
    autoOrder: { active: false, stores: [] },
  };
}
