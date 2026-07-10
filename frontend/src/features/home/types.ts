import type { Money } from '@/shared/api/types';
import type { MealDifficulty } from '@/features/mealplan/types';

/**
 * HomeViewModel — 홈 셸 주입 계약 (ui-design 2장).
 * 게스트 샘플과 회원 실데이터가 같은 형태로 주입된다.
 */

export type HomeMode = 'guest-default' | 'guest-planned' | 'member';

export type MealSlot = 'breakfast' | 'lunch' | 'dinner';

/** 레시피 시트 재료 칩 — name+quantity+unit (FR-504) */
export interface RecipeIngredient {
  name: string;
  quantity: string;
  unit: string;
}

export interface MealItem {
  slot: MealSlot;
  name: string;
  isSample: boolean;
  /** [member 옵셔널 확장] 재료명 목록 (FR-205) */
  ingredients?: string[];
  /** [member 옵셔널 확장] 끼니 추정 비용 — 재료 estCost 합 (FR-205) */
  estCost?: Money;
  /** [member 옵셔널 확장] 완료 토글 대상 끼니 id (FR-501) */
  mealId?: string;
  /** [member 옵셔널 확장] 레시피 시트 재료 칩 데이터 (FR-504) */
  recipeIngredients?: RecipeIngredient[];
  /** [member 옵셔널 확장] 조리 단계 (FR-502) — 없으면 시트가 기본 조리법 표시 */
  steps?: string[];
  /** [member 옵셔널 확장] 완료 시각 — 완료=ISO, 미완료=null (FR-501) */
  completedAt?: string | null;
  /** [member 옵셔널 확장] 조리 시간(분) — 없으면 기본값 (FR-505) */
  timeMinutes?: number | null;
  /** [member 옵셔널 확장] 조리 난이도 — 없으면 기본값 (FR-505) */
  difficulty?: MealDifficulty | null;
}

export interface DayPlan {
  /** 요일 코드 (mon..sun) — 표기는 i18n */
  day: string;
  /** [member 옵셔널 확장] 실제 일자 (YYYY-MM-DD) — 주간 스트립 이동 기준 */
  date?: string;
  meals: MealItem[];
}

export interface FridgeItem {
  name: string;
  quantity: string;
  /** 유통기한까지 남은 일수 — 2일 이하이면 임박 */
  expiresInDays: number;
}

export interface StoreBadge {
  id: string;
  name: string;
}

export interface HomeViewModel {
  mode: HomeMode;
  /** [member 옵셔널 확장] 주간 스트립에서 선택된 일자 (YYYY-MM-DD, FR-205) — 게스트 계약 불변 */
  selectedDate?: string;
  /** [member 옵셔널 확장] 예산 초과 여부 (budgetSummary.withinBudget=false, FR-206) */
  overBudget?: boolean;
  /** [member 옵셔널 확장] 표시 중인 식단 plan id — 재생성(FR-209) 대상 */
  planId?: string;
  budgetMood: {
    remaining: Money;
    saved: Money;
    wastePrevented: Money;
  };
  weekPlan: DayPlan[];
  fridgePreview: FridgeItem[];
  autoOrder: {
    active: boolean;
    nextOrderDate?: string;
    stores: StoreBadge[];
    /** 주문 추천 품목 (샘플 매트릭스 콘텐츠) — 선택 필드, 셸 계약 호환 확장 */
    recommendedItems?: string[];
  };
}

/** 유통기한 임박 판정 기준 (일) */
export const FRIDGE_EXPIRY_SOON_DAYS = 2;
