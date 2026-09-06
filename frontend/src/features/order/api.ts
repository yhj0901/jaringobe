import { apiFetch, type ApiResult } from '@/shared/api/client';
import type {
  OrderApproveRequest,
  OrderCreateRequest,
  OrderPreviewResponse,
  OrderResponse,
} from '@/features/order/types';

/**
 * order API 클라이언트 (api-spec 7장 v1.6) — shared/api/client 경유, httpOnly 쿠키.
 * 프론트는 POST /store/cart 를 직접 호출하지 않는다 (preview 가 서버에서 build_cart).
 */

/** GET /api/v1/orders/preview — 인증 필요. 저장 초안은 변경하지 않는 순수 조회. */
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

/** POST /api/v1/orders/{id}/approve — 서버 재계산 결과를 그대로 반환한다. */
export function approveOrder(
  id: string,
  body: OrderApproveRequest = {},
): Promise<ApiResult<OrderResponse>> {
  return apiFetch<OrderResponse>(`/api/v1/orders/${encodeURIComponent(id)}/approve`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** POST /api/v1/orders/{id}/recalculate — 열린 초안을 서버 데이터로 다시 계산한다. */
export function recalculateOrder(id: string): Promise<ApiResult<OrderResponse>> {
  return apiFetch<OrderResponse>(`/api/v1/orders/${encodeURIComponent(id)}/recalculate`, {
    method: 'POST',
  });
}

/** POST /api/v1/orders/{id}/cancel — 확정 주문 취소. */
export function cancelOrder(id: string): Promise<ApiResult<OrderResponse>> {
  return apiFetch<OrderResponse>(`/api/v1/orders/${encodeURIComponent(id)}/cancel`, {
    method: 'POST',
  });
}

/** POST /api/v1/orders/{id}/delivery — 배송 도착 여부 보정. */
export function confirmOrderDelivery(
  id: string,
  received: boolean,
): Promise<ApiResult<OrderResponse>> {
  return apiFetch<OrderResponse>(`/api/v1/orders/${encodeURIComponent(id)}/delivery`, {
    method: 'POST',
    body: JSON.stringify({ received }),
  });
}
