import { apiFetch, type ApiResult } from '@/shared/api/client';

/**
 * POST /api/v1/auth/logout (api-spec 1-4) — refresh 서버측 폐기 + 쿠키 삭제 (204).
 * visited 마커 기록·홈 이동은 호출측(설정 페이지) 담당 (FR-401, ui-design 9장).
 */
export function postLogout(): Promise<ApiResult<undefined>> {
  return apiFetch<undefined>('/api/v1/auth/logout', { method: 'POST' });
}
