import { create } from 'zustand';
import type { BridgePermissionStatus, BridgeReadyPayload } from '@/shared/bridge/protocol';

/**
 * 브리지 수신 상태 스토어 — 앱이 보낸 BRIDGE_READY/PERMISSION_STATUS/PUSH_TOKEN 을 보관한다.
 * 알림 설정 화면(OS 권한 배너)·soft ask·로그아웃 토큰 해제가 참조 (ui-design 12장).
 */
export interface BridgeState {
  /** BRIDGE_READY 수신 여부 + 앱 정보 */
  appInfo: BridgeReadyPayload | null;
  /** OS 푸시 권한 상태 — 수신 전 null */
  permission: BridgePermissionStatus | null;
  /** 이 기기의 푸시 토큰 — 로그아웃 시 DELETE 대상 (수신 전 null) */
  deviceToken: string | null;
  setAppInfo: (appInfo: BridgeReadyPayload) => void;
  setPermission: (permission: BridgePermissionStatus) => void;
  setDeviceToken: (deviceToken: string) => void;
  /** 테스트용 초기화 */
  reset: () => void;
}

export const useBridgeStore = create<BridgeState>((set) => ({
  appInfo: null,
  permission: null,
  deviceToken: null,
  setAppInfo: (appInfo) => set({ appInfo }),
  setPermission: (permission) => set({ permission }),
  setDeviceToken: (deviceToken) => set({ deviceToken }),
  reset: () => set({ appInfo: null, permission: null, deviceToken: null }),
}));
