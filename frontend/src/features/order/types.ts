import type { Country, Money } from '@/shared/api/types';
import type { StoreId } from '@/features/store/types';

/**
 * order 도메인 API 타입 — docs/설계/api-spec.md 7장(v1.6)과 1:1 일치 (camelCase).
 * P0 는 시뮬레이션 확정만. status=confirmed (paid 도입 금지).
 */

/** GET /api/v1/orders/preview 라인 (needed | covered) */
export interface OrderPreviewLine {
  name: string;
  unit: string;
  needed: string;
  fromFridge: string;
  toBuy: string;
}

/** preview.cart.items[] — 네이버 매칭 결과 (미매칭이면 matched=false) */
export interface OrderCartItem {
  ingredient: string;
  matched: boolean;
  title: string | null;
  price: Money | null;
  mallName: string | null;
  link: string | null;
  candidateCount: number;
}

export interface OrderCart {
  items: OrderCartItem[];
  total: Money;
  matchedCount: number;
  notes: string[];
}

/** GET /api/v1/orders/preview — 200 OrderPreviewResponse (api-spec 7-1) */
export interface OrderPreviewResponse {
  mealPlanId: string;
  storeConnected: boolean;
  country: Country | string;
  needed: OrderPreviewLine[];
  covered: OrderPreviewLine[];
  cart: OrderCart;
  estimatedTotal: Money;
  notes: string[];
}

export type OrderStatus = 'confirmed';
export type OrderFrequency = 'weekly';
export type OrderLineType = 'needed' | 'covered';

/** POST /api/v1/orders 요청 — 라인 목록 필드 없음 (CWE-602, extra forbid) */
export interface OrderCreateRequest {
  store: StoreId;
}

/** 주문 스냅샷 라인 (api-spec 7-2 items[]) */
export interface OrderItem {
  name: string;
  quantity: string;
  unit: string;
  lineType: OrderLineType;
  matched: boolean;
  title: string | null;
  unitPrice: Money | null;
}

/** POST /api/v1/orders 201 · GET /api/v1/orders/latest 200 (api-spec 7-2/7-3) */
export interface OrderResponse {
  id: string;
  store: StoreId;
  status: OrderStatus;
  frequency: OrderFrequency;
  nextSuggestedAt: string;
  estimatedTotal: Money;
  confirmedAt: string;
  simulation: boolean;
  items: OrderItem[];
}

export const MEALPLAN_NOT_FOUND_CODE = 'MEALPLAN_NOT_FOUND';
export const ORDER_NOT_FOUND_CODE = 'ORDER_NOT_FOUND';
export const STORE_NOT_CONNECTED_CODE = 'STORE_NOT_CONNECTED';
export const NOTHING_TO_ORDER_CODE = 'NOTHING_TO_ORDER';

/** 홈 카드 추천 칩 최대 개수 — 초과분은 +K (ui-design 13장) */
export const RECOMMENDED_CHIP_CAP = 6;
