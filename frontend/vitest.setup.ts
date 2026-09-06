import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';

/**
 * Node 20+ 의 실험적 Web Storage 대응.
 *
 * Node 는 전역에 localStorage/sessionStorage 를 노출하는데, `--localstorage-file`
 * 없이는 clear() 조차 없는 반쪽짜리 객체다. 이것이 jsdom 구현을 가려서
 * `window.localStorage.clear is not a function` 으로 전 테스트가 깨진다.
 * (Node 25 에서 확인. `--no-experimental-webstorage` 플래그로도 피할 수 있지만
 *  실행 환경마다 플래그를 맞추는 대신 여기서 확정적으로 고정한다.)
 *
 * 사용 가능한 Storage 가 아니면 인메모리 구현으로 교체한다.
 */
function installMemoryStorage(key: 'localStorage' | 'sessionStorage'): void {
  const existing = window[key] as Storage | undefined;
  if (existing && typeof existing.clear === 'function') return;

  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    getItem: (k: string) => (store.has(k) ? (store.get(k) as string) : null),
    setItem: (k: string, v: string) => void store.set(String(k), String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  };

  Object.defineProperty(window, key, { value: storage, configurable: true, writable: true });
}

installMemoryStorage('localStorage');
installMemoryStorage('sessionStorage');

afterEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});
