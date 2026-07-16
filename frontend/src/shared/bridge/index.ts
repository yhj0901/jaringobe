import { APP_UA_MARKER, parseAppMessage, type AppToWebMessage, type WebToAppMessage } from '@/shared/bridge/protocol';

/**
 * 웹 쪽 브리지 모듈 (ui-design 12장) — isApp / onBridgeMessage / sendToApp.
 * 프로토콜·버저닝 규칙은 mobile-app.md 3장이 원본.
 */

declare global {
  interface Window {
    /** react-native-webview 가 주입하는 postMessage 채널 (앱 내에서만 존재) */
    ReactNativeWebView?: { postMessage: (message: string) => void };
  }
}

/** 앱 내 실행 감지 — UA 'JaringobeApp/' + window.ReactNativeWebView 이중 확인 (ui-design 12장) */
export function isApp(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    window.navigator.userAgent.includes(APP_UA_MARKER) && window.ReactNativeWebView !== undefined
  );
}

/**
 * 웹 → 앱 전송 — 앱 밖(브리지 부재)에서는 무시하고 false 반환.
 */
export function sendToApp(message: WebToAppMessage): boolean {
  if (typeof window === 'undefined' || window.ReactNativeWebView === undefined) return false;
  window.ReactNativeWebView.postMessage(JSON.stringify(message));
  return true;
}

/**
 * 앱 → 웹 수신 구독 — 해제 함수 반환.
 * RN WebView 는 iOS=window / Android=document 에 message 이벤트를 디스패치하므로 양쪽 모두 구독.
 */
export function onBridgeMessage(handler: (message: AppToWebMessage) => void): () => void {
  const listener = (event: Event) => {
    const message = parseAppMessage((event as MessageEvent).data);
    if (message !== null) handler(message);
  };
  window.addEventListener('message', listener);
  document.addEventListener('message', listener);
  return () => {
    window.removeEventListener('message', listener);
    document.removeEventListener('message', listener);
  };
}

export type { AppToWebMessage, WebToAppMessage };
export { BRIDGE_VERSION, APP_UA_MARKER } from '@/shared/bridge/protocol';
export type {
  BridgePermissionStatus,
  BridgePlatform,
  BridgeReadyPayload,
  PermissionStatusPayload,
  PushTokenPayload,
} from '@/shared/bridge/protocol';
