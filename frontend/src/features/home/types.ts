import type { Money } from '@/shared/api/types';

/**
 * HomeViewModel — 홈 셸 주입 계약 (ui-design 2장).
 * 게스트 샘플과 회원 실데이터가 같은 형태로 주입된다.
 */

export type HomeMode = 'guest-default' | 'guest-planned' | 'member';

export type MealSlot = 'breakfast' | 'lunch' | 'dinner';

export interface MealItem {
  slot: MealSlot;
  name: string;
  isSample: boolean;
}

export interface DayPlan {
  /** 요일 코드 (mon..sun) — 표기는 i18n */
  day: string;
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
