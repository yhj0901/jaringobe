import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { BridgeProvider } from '@/features/notification/BridgeProvider';
import { registerPushToken } from '@/features/notification/deviceRegistration';
import { useBridgeStore } from '@/shared/bridge/store';
import { stubAppEnvironment, type AppEnvStub } from '@/test/appEnv';

vi.mock('@/features/notification/deviceRegistration', () => ({
  registerPushToken: vi.fn().mockResolvedValue(true),
}));

const registerMock = vi.mocked(registerPushToken);

let app: AppEnvStub | null = null;

function dispatch(data: unknown) {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', { data }));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useBridgeStore.getState().reset();
});

afterEach(() => {
  app?.restore();
  app = null;
});

describe('BridgeProvider (ui-design 12장 — 앱 브리지 글로벌 리스너)', () => {
  it('앱 내: 구독 완료 직후 SYNC_REQUEST 를 1회 발신한다 (BUG-006 — 초기 메시지 유실 대응)', () => {
    app = stubAppEnvironment();
    render(<BridgeProvider />);

    expect(app.postMessage).toHaveBeenCalledTimes(1);
    expect(app.postMessage).toHaveBeenCalledWith(
      JSON.stringify({ v: 1, type: 'SYNC_REQUEST', payload: {} }),
    );
  });

  it('SYNC_REQUEST 발신 시점에 이미 구독 중 — 직후 도착한 재발신 메시지를 수신한다 (BUG-006)', () => {
    app = stubAppEnvironment();
    render(<BridgeProvider />);
    expect(app.postMessage).toHaveBeenCalledTimes(1); // 구독 완료 후 발신

    // 앱이 SYNC_REQUEST 에 응답해 재발신한 상태 메시지가 유실 없이 반영된다
    dispatch(JSON.stringify({ v: 1, type: 'BRIDGE_READY', payload: { appVersion: '1.0.0', platform: 'android' } }));
    dispatch(JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'granted' } }));
    expect(useBridgeStore.getState().appInfo).toEqual({ appVersion: '1.0.0', platform: 'android' });
    expect(useBridgeStore.getState().permission).toBe('granted');
  });

  it('앱 내: BRIDGE_READY/PERMISSION_STATUS 를 스토어에 반영한다', () => {
    app = stubAppEnvironment();
    render(<BridgeProvider />);

    dispatch(JSON.stringify({ v: 1, type: 'BRIDGE_READY', payload: { appVersion: '1.2.0', platform: 'ios' } }));
    dispatch(JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'undetermined' } }));

    expect(useBridgeStore.getState().appInfo).toEqual({ appVersion: '1.2.0', platform: 'ios' });
    expect(useBridgeStore.getState().permission).toBe('undetermined');
  });

  it('PUSH_TOKEN → 스토어 보관 + 디바이스 등록 호출', () => {
    app = stubAppEnvironment();
    render(<BridgeProvider />);

    const payload = {
      token: 'ExponentPushToken[abc]',
      platform: 'android',
      locale: 'en-US',
      timezone: 'America/New_York',
      appVersion: '1.0.0',
    };
    dispatch(JSON.stringify({ v: 1, type: 'PUSH_TOKEN', payload }));

    expect(useBridgeStore.getState().deviceToken).toBe('ExponentPushToken[abc]');
    expect(registerMock).toHaveBeenCalledWith(payload);
  });

  it('앱 밖(웹 브라우저)에서는 구독하지 않는다', () => {
    render(<BridgeProvider />);
    dispatch(JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'granted' } }));
    expect(useBridgeStore.getState().permission).toBeNull();
  });

  it('언마운트 시 구독을 해제한다', () => {
    app = stubAppEnvironment();
    const { unmount } = render(<BridgeProvider />);
    unmount();
    dispatch(JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'granted' } }));
    expect(useBridgeStore.getState().permission).toBeNull();
  });
});
