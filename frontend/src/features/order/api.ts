import { apiFetch, type ApiResult } from '@/shared/api/client';
import type {
  OrderCreateRequest,
  OrderPreviewResponse,
  OrderResponse,
} from '@/features/order/types';

/**
 * order API 클라이언트 (api-spec 7장 v1.6) — shared/api/client 경유, httpOnly 쿠키.
 * 프론트는 POST /store/cart 를 직접 호출하지 않는다 (preview 가 서버에서 build_cart).
 */

/** GET /api/v1/orders/preview — 인증 필요. 연동 없어도 200. 404 MEALPLAN_NOT_FOUND */
export function fetchOrderPreview(): Promise<ApiResult<OrderPreviewResponse>> {
  return apiFetch<OrderPreviewResponse>('/api/v1/orders/preview');
}

/**
 * POST /api/v1/orders — body `{ store }` 만 (CWE-602: 라인·가격 클라이언트 전달 금지).
 * 서버가 preview 를 재계산해 confirmed 스냅샷 + fridge inbound.
 */
export function createOrder(body: OrderCreateRequest): Promise<ApiResult<OrderResponse>> {
  return apiFetch<OrderResponse>('/api/v1/orders', {
    method: 'POST',
    body: JSON.stringify({ store: body.store }),
  });
}

/** GET /api/v1/orders/latest — 없으면 404 ORDER_NOT_FOUND */
export function fetchLatestOrder(): Promise<ApiResult<OrderResponse>> {
  return apiFetch<OrderResponse>('/api/v1/orders/latest');
}
