/**
 * store 도메인 API 타입 — docs/설계/api-spec.md 6장(v1.3)과 1:1 일치 (camelCase).
 * 1단계: 연동 상태 관리만 (자격증명 미수집 — FR-404/405).
 */

/** KR 지원 스토어 (api-spec 6-2 열거값 — 그 외 404 STORE_NOT_SUPPORTED) */
export type StoreId = 'kurly' | 'coupang' | 'ssg' | 'naver';

export type StoreConnectionStatus = 'connected' | 'disconnected';

/** GET /api/v1/stores/connections 응답 항목 (api-spec 6-1) */
export interface StoreConnection {
  store: StoreId;
  status: StoreConnectionStatus;
  connectedAt: string | null;
}

/** GET /api/v1/stores/connections — 200 (KR 4종 전체, 미저장 스토어는 disconnected) */
export interface StoreConnectionsResponse {
  connections: StoreConnection[];
}

/** PUT /api/v1/stores/connections/{store} 요청 (api-spec 6-2) */
export interface StoreConnectionUpdateRequest {
  connected: boolean;
}
