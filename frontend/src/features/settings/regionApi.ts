import { apiFetch, type ApiResult } from '@/shared/api/client';
import type { Country, UserMeResponse } from '@/shared/api/types';

/**
 * 지역 전환 API 클라이언트 (api-spec 1-6 v1.5) — shared/api/client 경유.
 * currency 는 서버가 country 로부터 매핑하므로 요청에 포함하지 않는다.
 */

/** PUT /api/v1/users/me/region — 지역 수동 전환, 200 UserMeResponse(country/currency 갱신) */
export function putUserRegion(country: Country): Promise<ApiResult<UserMeResponse>> {
  return apiFetch<UserMeResponse>('/api/v1/users/me/region', {
    method: 'PUT',
    body: JSON.stringify({ country }),
  });
}
