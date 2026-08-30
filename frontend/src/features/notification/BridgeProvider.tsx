'use client';

import { useEffect } from 'react';
import { BRIDGE_VERSION, isApp, onBridgeMessage, sendToApp } from '@/shared/bridge';
import { useBridgeStore } from '@/shared/bridge/store';
import { registerPushToken } from '@/features/notification/deviceRegistration';

/**
 * 앱 브리지 글로벌 리스너 (ui-design 12장) — 로캘 레이아웃에 1회 마운트.
 * 앱 내에서만 동작: BRIDGE_READY/PERMISSION_STATUS 를 스토어에 반영하고,
 * PUSH_TOKEN 수신 시 디바이스 등록(미로그인이면 메모리 보류)을 수행한다.
 */
export function BridgeProvider() {
  useEffect(() => {
    if (!isApp()) return undefined;
    const unsubscribe = onBridgeMessage((message) => {
      const store = useBridgeStore.getState();
      switch (message.type) {
        case 'BRIDGE_READY':
          store.setAppInfo(message.payload);
          break;
        case 'PERMISSION_STATUS':
          store.setPermission(message.payload.status);
          break;
        case 'PUSH_TOKEN':
          store.setDeviceToken(message.payload.token);
          void registerPushToken(message.payload);
          break;
      }
    });
    // 구독 완료 직후 앱 상태 재발신 요청 — 초기 메시지 유실 대응 (BUG-006, mobile-app 3장).
    // 구버전 앱은 미지 type 무시 — 응답 부재를 오류로 취급하지 않는다.
    sendToApp({ v: BRIDGE_VERSION, type: 'SYNC_REQUEST', payload: {} });
    return unsubscribe;
  }, []);

  return null;
}
