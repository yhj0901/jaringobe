import { apiFetch, type ApiResult } from '@/shared/api/client';

/** 백엔드 fridge 도메인 응답 (api-reference: FridgeItemRead) */
export interface FridgeItem {
  id: string;
  name: string;
  quantity: string;
  unit: string;
  expiresAt: string | null;
  source: string;
  createdAt: string;
}

export interface FridgeItemInput {
  name: string;
  quantity: string;
  unit: string;
  expiresAt?: string | null;
  source?: 'manual' | 'delivery' | 'mealplan';
}

/** GET /api/v1/fridge — 재고 목록(유통기한 임박순) */
export function listFridge(): Promise<ApiResult<FridgeItem[]>> {
  return apiFetch<FridgeItem[]>('/api/v1/fridge');
}

/** POST /api/v1/fridge/items — 재료 추가(단건/복수) */
export function addFridgeItems(items: FridgeItemInput[]): Promise<ApiResult<FridgeItem[]>> {
  return apiFetch<FridgeItem[]>('/api/v1/fridge/items', {
    method: 'POST',
    body: JSON.stringify({ items }),
  });
}

/** DELETE /api/v1/fridge/items/{id} */
export function deleteFridgeItem(id: string): Promise<ApiResult<void>> {
  return apiFetch<void>(`/api/v1/fridge/items/${id}`, { method: 'DELETE' });
}

/** 유통기한까지 남은 일수 (없으면 null) */
export function daysUntil(expiresAt: string | null): number | null {
  if (!expiresAt) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(`${expiresAt}T00:00:00`);
  return Math.round((due.getTime() - today.getTime()) / 86_400_000);
}
