/**
 * 웹↔앱 브리지 프로토콜 (docs/설계/mobile-app.md 3장이 원본 — 웹·앱 공용 계약).
 * 전 메시지 공통 `{ v: 1, type, payload }` — 알 수 없는 type/상위 v 는 무시 (전방 호환, 에러 금지).
 */

export const BRIDGE_VERSION = 1 as const;

/** 앱 내 실행 감지용 UA 접미사 마커 (mobile-app 4장: ` JaringobeApp/{appVersion} ({ios|android})`) */
export const APP_UA_MARKER = 'JaringobeApp/';

export type BridgePlatform = 'ios' | 'android';
export type BridgePermissionStatus = 'granted' | 'denied' | 'undetermined';

/** BRIDGE_READY — 웹뷰 로드 완료 직후 1회 */
export interface BridgeReadyPayload {
  appVersion: string;
  platform: BridgePlatform;
}

/** PERMISSION_STATUS — READY 직후 + 변경 시 */
export interface PermissionStatusPayload {
  status: BridgePermissionStatus;
}

/** PUSH_TOKEN — 권한 granted 후 발급/변경 시 */
export interface PushTokenPayload {
  token: string;
  platform: BridgePlatform;
  locale: string;
  timezone: string;
  appVersion: string;
}

/** 앱 → 웹 메시지 (웹 `message` 이벤트 수신) */
export type AppToWebMessage =
  | { v: typeof BRIDGE_VERSION; type: 'BRIDGE_READY'; payload: BridgeReadyPayload }
  | { v: typeof BRIDGE_VERSION; type: 'PERMISSION_STATUS'; payload: PermissionStatusPayload }
  | { v: typeof BRIDGE_VERSION; type: 'PUSH_TOKEN'; payload: PushTokenPayload };

/** 웹 → 앱 메시지 (`window.ReactNativeWebView.postMessage`) */
export type WebToAppMessage =
  | { v: typeof BRIDGE_VERSION; type: 'REQUEST_PUSH_PERMISSION'; payload: Record<string, never> }
  | { v: typeof BRIDGE_VERSION; type: 'OPEN_OS_SETTINGS'; payload: Record<string, never> }
  | {
      v: typeof BRIDGE_VERSION;
      type: 'LOGIN_PROVIDER';
      payload: { provider: 'kakao' | 'google' | 'apple'; next: string };
    }
  /** SYNC_REQUEST — 웹 구독 완료 직후 앱 상태 재발신 요청 (BUG-006, mobile-app 3장 v1 증보. 구버전 앱은 무시 — 응답 부재는 오류 아님) */
  | { v: typeof BRIDGE_VERSION; type: 'SYNC_REQUEST'; payload: Record<string, never> };

const PLATFORMS: readonly string[] = ['ios', 'android'];
const PERMISSION_STATUSES: readonly string[] = ['granted', 'denied', 'undetermined'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isBridgeReadyPayload(payload: Record<string, unknown>): payload is Record<string, unknown> & BridgeReadyPayload {
  return typeof payload.appVersion === 'string' && PLATFORMS.includes(payload.platform as string);
}

function isPermissionStatusPayload(
  payload: Record<string, unknown>,
): payload is Record<string, unknown> & PermissionStatusPayload {
  return PERMISSION_STATUSES.includes(payload.status as string);
}

function isPushTokenPayload(payload: Record<string, unknown>): payload is Record<string, unknown> & PushTokenPayload {
  return (
    typeof payload.token === 'string' &&
    payload.token.length > 0 &&
    PLATFORMS.includes(payload.platform as string) &&
    typeof payload.locale === 'string' &&
    typeof payload.timezone === 'string' &&
    typeof payload.appVersion === 'string'
  );
}

/**
 * 앱 → 웹 메시지 파싱 — 문자열(JSON)/객체 모두 허용.
 * 규약 위반·미지 type·상위 v 는 null (무시 — mobile-app 3장 전방 호환).
 */
export function parseAppMessage(raw: unknown): AppToWebMessage | null {
  let data: unknown = raw;
  if (typeof raw === 'string') {
    try {
      data = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!isRecord(data)) return null;
  if (data.v !== BRIDGE_VERSION) return null; // 상위/미지 버전 무시
  const payload = data.payload;
  if (!isRecord(payload)) return null;

  switch (data.type) {
    case 'BRIDGE_READY':
      return isBridgeReadyPayload(payload)
        ? { v: BRIDGE_VERSION, type: 'BRIDGE_READY', payload: { appVersion: payload.appVersion, platform: payload.platform } }
        : null;
    case 'PERMISSION_STATUS':
      return isPermissionStatusPayload(payload)
        ? { v: BRIDGE_VERSION, type: 'PERMISSION_STATUS', payload: { status: payload.status } }
        : null;
    case 'PUSH_TOKEN':
      return isPushTokenPayload(payload)
        ? {
            v: BRIDGE_VERSION,
            type: 'PUSH_TOKEN',
            payload: {
              token: payload.token,
              platform: payload.platform,
              locale: payload.locale,
              timezone: payload.timezone,
              appVersion: payload.appVersion,
            },
          }
        : null;
    default:
      return null; // 알 수 없는 type 무시
  }
}
