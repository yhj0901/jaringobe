import { sanitizeInternalPath } from './deeplink';

/**
 * 웹↔앱 브리지 프로토콜 (docs/설계/mobile-app.md 3장이 원본 — 웹·앱 공용 계약).
 * 웹 쪽 대응 모듈: frontend/src/shared/bridge/protocol.ts
 * 전 메시지 공통 `{ v: 1, type, payload }` — 알 수 없는 type/상위 v 는 무시 (에러 금지).
 * 직렬화/파싱은 순수 함수로 분리 (단위 테스트 대상).
 */

export const BRIDGE_VERSION = 1 as const;

export type BridgePlatform = 'ios' | 'android';
export type PermissionStatus = 'granted' | 'denied' | 'undetermined';
export type LoginProvider = 'kakao' | 'google' | 'apple';

export interface PushTokenPayload {
  token: string;
  platform: BridgePlatform;
  locale: string;
  timezone: string;
  appVersion: string;
}

/** 앱 → 웹 (webViewRef.postMessage) */
export type AppToWebMessage =
  | { v: typeof BRIDGE_VERSION; type: 'BRIDGE_READY'; payload: { appVersion: string; platform: BridgePlatform } }
  | { v: typeof BRIDGE_VERSION; type: 'PERMISSION_STATUS'; payload: { status: PermissionStatus } }
  | { v: typeof BRIDGE_VERSION; type: 'PUSH_TOKEN'; payload: PushTokenPayload };

/** 웹 → 앱 (window.ReactNativeWebView.postMessage) */
export type WebToAppMessage =
  | { v: typeof BRIDGE_VERSION; type: 'REQUEST_PUSH_PERMISSION'; payload: Record<string, never> }
  | { v: typeof BRIDGE_VERSION; type: 'OPEN_OS_SETTINGS'; payload: Record<string, never> }
  | { v: typeof BRIDGE_VERSION; type: 'LOGIN_PROVIDER'; payload: { provider: LoginProvider; next: string } }
  | { v: typeof BRIDGE_VERSION; type: 'SYNC_REQUEST'; payload: Record<string, never> };

const LOGIN_PROVIDERS: readonly string[] = ['kakao', 'google', 'apple'];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** 앱 → 웹 메시지 직렬화 */
export function serializeAppMessage(message: AppToWebMessage): string {
  return JSON.stringify(message);
}

/**
 * 웹 → 앱 메시지 파싱 (onMessage) — 규약 위반·미지 type·상위 v 는 null (무시, CWE-345).
 * LOGIN_PROVIDER 의 next 는 내부 상대경로로 위생 처리 (CWE-601).
 */
export function parseWebMessage(raw: unknown): WebToAppMessage | null {
  if (typeof raw !== 'string') return null;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(data)) return null;
  if (data.v !== BRIDGE_VERSION) return null; // 상위/미지 버전 무시 (전방 호환)
  const payload = data.payload;
  if (!isRecord(payload)) return null;

  switch (data.type) {
    case 'REQUEST_PUSH_PERMISSION':
      return { v: BRIDGE_VERSION, type: 'REQUEST_PUSH_PERMISSION', payload: {} };
    case 'OPEN_OS_SETTINGS':
      return { v: BRIDGE_VERSION, type: 'OPEN_OS_SETTINGS', payload: {} };
    case 'SYNC_REQUEST':
      // 웹 구독 완료 직후 앱 상태 재발신 요청 (BUG-006 — mobile-app 3장 v1 증보)
      return { v: BRIDGE_VERSION, type: 'SYNC_REQUEST', payload: {} };
    case 'LOGIN_PROVIDER': {
      const provider = payload.provider;
      if (typeof provider !== 'string' || !LOGIN_PROVIDERS.includes(provider)) return null;
      return {
        v: BRIDGE_VERSION,
        type: 'LOGIN_PROVIDER',
        payload: {
          provider: provider as LoginProvider,
          next: sanitizeInternalPath(payload.next),
        },
      };
    }
    default:
      return null; // 알 수 없는 type 무시
  }
}
