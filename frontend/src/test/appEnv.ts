import { vi, type Mock } from 'vitest';

/**
 * 앱 웹뷰 환경 스텁 — UA 'JaringobeApp/' 접미사 + window.ReactNativeWebView 주입.
 * isApp() 이중 확인(ui-design 12장)을 만족시키는 테스트 헬퍼.
 */
export interface AppEnvStub {
  postMessage: Mock;
  restore: () => void;
}

export function stubAppEnvironment(): AppEnvStub {
  const originalDescriptor = Object.getOwnPropertyDescriptor(window.navigator, 'userAgent');
  Object.defineProperty(window.navigator, 'userAgent', {
    configurable: true,
    get: () => 'Mozilla/5.0 (jsdom) JaringobeApp/1.0.0 (ios)',
  });

  const postMessage = vi.fn();
  window.ReactNativeWebView = { postMessage };

  return {
    postMessage,
    restore: () => {
      if (originalDescriptor !== undefined) {
        Object.defineProperty(window.navigator, 'userAgent', originalDescriptor);
      } else {
        Reflect.deleteProperty(window.navigator, 'userAgent');
      }
      delete window.ReactNativeWebView;
    },
  };
}
