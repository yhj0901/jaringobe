import { apiFetch, type ApiResult } from '@/shared/api/client';
import type { CycleSettingsUpdate, CycleState } from '@/features/cycle/types';

/** GET /api/v1/cycle — 설정이 없으면 서버가 기본값을 lazy 생성한다. */
export function fetchCycle(): Promise<ApiResult<CycleState>> {
  return apiFetch<CycleState>('/api/v1/cycle');
}

/** PUT /api/v1/cycle/settings — 보낸 필드만 부분 갱신한다. */
export function putCycleSettings(body: CycleSettingsUpdate): Promise<ApiResult<CycleState>> {
  return apiFetch<CycleState>('/api/v1/cycle/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/** POST /api/v1/cycle/skip — 현재 사이클 1회 건너뛰기. */
export function postCycleSkip(): Promise<ApiResult<CycleState>> {
  return apiFetch<CycleState>('/api/v1/cycle/skip', { method: 'POST' });
}
