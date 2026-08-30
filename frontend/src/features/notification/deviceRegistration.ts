import { registerDevice } from '@/features/notification/api';
import type { DeviceRegisterRequest } from '@/features/notification/types';
import type { PushTokenPayload } from '@/shared/bridge/protocol';

/**
 * PUSH_TOKEN 수신 → 디바이스 등록 흐름 (ui-design 12장).
 * 로그인 상태면 즉시 PUT /notifications/devices, 미로그인(401)이면 메모리 보류 후
 * 로그인 완료(?login=success) 시 flushPendingDeviceToken() 으로 등록한다.
 */

let pendingRequest: DeviceRegisterRequest | null = null;

/** 브리지 payload → 등록 요청 변환 — locale 은 서버 허용값(ko|en)으로 정규화 */
export function toDeviceRegisterRequest(payload: PushTokenPayload): DeviceRegisterRequest {
  return {
    token: payload.token,
    platform: payload.platform,
    locale: payload.locale.toLowerCase().startsWith('ko') ? 'ko' : 'en',
    timezone: payload.timezone,
    appVersion: payload.appVersion,
  };
}

/** PUSH_TOKEN 수신 처리 — 성공 true. 401 은 로그인 대기 보류(pending) */
export async function registerPushToken(payload: PushTokenPayload): Promise<boolean> {
  const request = toDeviceRegisterRequest(payload);
  pendingRequest = null;
  const result = await registerDevice(request);
  if (result.ok) return true;
  if (result.status === 401) pendingRequest = request; // 미로그인 — 메모리 보류
  return false;
}

/** 로그인 완료 후 보류 토큰 등록 (ui-design 12장) — 여전히 401 이면 보류 유지 */
export async function flushPendingDeviceToken(): Promise<void> {
  const request = pendingRequest;
  if (request === null) return;
  pendingRequest = null;
  const result = await registerDevice(request);
  if (!result.ok && result.status === 401) pendingRequest = request;
}

/** 보류 중 토큰 존재 여부 (테스트/디버그용) */
export function hasPendingDeviceToken(): boolean {
  return pendingRequest !== null;
}

/** 테스트용 초기화 */
export function resetDeviceRegistration(): void {
  pendingRequest = null;
}
