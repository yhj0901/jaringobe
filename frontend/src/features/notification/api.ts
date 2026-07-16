import { apiFetch, type ApiResult } from '@/shared/api/client';
import type {
  DeviceRegisterRequest,
  DeviceRegisterResponse,
  NotificationSettingUpdate,
  NotificationSettingsResponse,
} from '@/features/notification/types';

/**
 * notification API 클라이언트 (api-spec 6-A v1.5) — shared/api/client 경유.
 */

/** PUT /api/v1/notifications/devices — 토큰 idempotent upsert (api-spec 6-A-1) */
export function registerDevice(
  request: DeviceRegisterRequest,
): Promise<ApiResult<DeviceRegisterResponse>> {
  return apiFetch<DeviceRegisterResponse>('/api/v1/notifications/devices', {
    method: 'PUT',
    body: JSON.stringify(request),
  });
}

/** DELETE /api/v1/notifications/devices/{token} — 로그아웃 시 해제, 없는 토큰도 204 (api-spec 6-A-2) */
export function deleteDevice(token: string): Promise<ApiResult<undefined>> {
  return apiFetch<undefined>(
    `/api/v1/notifications/devices/${encodeURIComponent(token)}`,
    { method: 'DELETE' },
  );
}

/** GET /api/v1/notifications/settings — 없으면 서버가 기본값 lazy 생성 (api-spec 6-A-3) */
export function fetchNotificationSettings(): Promise<ApiResult<NotificationSettingsResponse>> {
  return apiFetch<NotificationSettingsResponse>('/api/v1/notifications/settings');
}

/** PUT /api/v1/notifications/settings — 부분 갱신, 전체 settings 재반환 (api-spec 6-A-4) */
export function putNotificationSettings(
  updates: NotificationSettingUpdate[],
): Promise<ApiResult<NotificationSettingsResponse>> {
  return apiFetch<NotificationSettingsResponse>('/api/v1/notifications/settings', {
    method: 'PUT',
    body: JSON.stringify({ settings: updates }),
  });
}
