import { afterEach, describe, expect, it, vi } from 'vitest';
import { isApp, onBridgeMessage, sendToApp } from '@/shared/bridge';
import { stubAppEnvironment, type AppEnvStub } from '@/test/appEnv';

let app: AppEnvStub | null = null;

afterEach(() => {
  app?.restore();
  app = null;
});

describe('isApp — UA + ReactNativeWebView 이중 확인 (ui-design 12장)', () => {
  it('일반 브라우저(jsdom 기본)에서는 false', () => {
    expect(isApp()).toBe(false);
  });

  it('UA 마커 + 브리지 객체가 모두 있으면 true', () => {
    app = stubAppEnvironment();
    expect(isApp()).toBe(true);
  });

  it('브리지 객체만 있고 UA 마커가 없으면 false (스푸핑 방지 이중 확인)', () => {
    window.ReactNativeWebView = { postMessage: vi.fn() };
    try {
      expect(isApp()).toBe(false);
    } finally {
      delete window.ReactNativeWebView;
    }
  });
});

describe('sendToApp', () => {
  it('앱 내: JSON 직렬화해 postMessage 로 전달한다', () => {
    app = stubAppEnvironment();
    const sent = sendToApp({ v: 1, type: 'REQUEST_PUSH_PERMISSION', payload: {} });
    expect(sent).toBe(true);
    expect(app.postMessage).toHaveBeenCalledWith(
      JSON.stringify({ v: 1, type: 'REQUEST_PUSH_PERMISSION', payload: {} }),
    );
  });

  it('앱 밖(브리지 부재)에서는 무시하고 false', () => {
    expect(sendToApp({ v: 1, type: 'OPEN_OS_SETTINGS', payload: {} })).toBe(false);
  });
});

describe('onBridgeMessage — window/document 양쪽 구독 + 해제', () => {
  function dispatchMessage(target: Window | Document, data: unknown) {
    target.dispatchEvent(new MessageEvent('message', { data }));
  }

  it('window 로 온 유효 메시지를 핸들러에 전달하고, 무효 메시지는 무시한다', () => {
    const handler = vi.fn();
    const off = onBridgeMessage(handler);

    dispatchMessage(window, JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'granted' } }));
    dispatchMessage(window, JSON.stringify({ v: 9, type: 'PERMISSION_STATUS', payload: { status: 'granted' } }));
    dispatchMessage(window, 'garbage');

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith({
      v: 1,
      type: 'PERMISSION_STATUS',
      payload: { status: 'granted' },
    });
    off();
  });

  it('document(Android RN WebView) 디스패치도 수신한다', () => {
    const handler = vi.fn();
    const off = onBridgeMessage(handler);
    dispatchMessage(
      document,
      JSON.stringify({ v: 1, type: 'BRIDGE_READY', payload: { appVersion: '1.0.0', platform: 'android' } }),
    );
    expect(handler).toHaveBeenCalledTimes(1);
    off();
  });

  it('해제 함수 호출 후에는 수신하지 않는다', () => {
    const handler = vi.fn();
    const off = onBridgeMessage(handler);
    off();
    dispatchMessage(window, JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'denied' } }));
    dispatchMessage(document, JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'denied' } }));
    expect(handler).not.toHaveBeenCalled();
  });
});
