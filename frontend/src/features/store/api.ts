import { apiFetch, type ApiResult } from '@/shared/api/client';
import type { StoreConnectionsResponse, StoreId } from '@/features/store/types';

/**
 * store 연동 상태 API 클라이언트 (api-spec 6장 v1.3) — shared/api/client 경유.
 * 1단계: 연동 상태 관리만 — 자격증명 미수집 (FR-404/405).
 */

/** GET /api/v1/stores/connections — KR 4종 전체 상태 (api-spec 6-1) */
export function fetchStoreConnections(): Promise<ApiResult<StoreConnectionsResponse>> {
  return apiFetch<StoreConnectionsResponse>('/api/v1/stores/connections');
}

/**
 * PUT /api/v1/stores/connections/{store} — 연동 표시 upsert (api-spec 6-2).
 * 응답 본문은 계약 미확정(200) — 상태 갱신은 요청 의도 기준으로 처리한다.
 */
export function putStoreConnection(store: StoreId, connected: boolean): Promise<ApiResult<unknown>> {
  return apiFetch<unknown>(`/api/v1/stores/connections/${encodeURIComponent(store)}`, {
    method: 'PUT',
    body: JSON.stringify({ connected }),
  });
}
