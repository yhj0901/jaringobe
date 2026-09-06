import {
  BRIDGE_VERSION,
  parseWebMessage,
  serializeAppMessage,
} from '../src/bridge';

/**
 * 브리지 프로토콜 순수 함수 단위 테스트 (mobile-app 8장 — jest-expo).
 * 실행: mobile/ 에서 `npm install` 후 `npm test` (네트워크 필요 — CI/로컬에서 실행).
 */

describe('serializeAppMessage', () => {
  it('앱 → 웹 메시지를 v1 JSON 으로 직렬화한다', () => {
    const json = serializeAppMessage({
      v: BRIDGE_VERSION,
      type: 'PERMISSION_STATUS',
      payload: { status: 'granted' },
    });
    expect(JSON.parse(json)).toEqual({
      v: 1,
      type: 'PERMISSION_STATUS',
      payload: { status: 'granted' },
    });
  });

  it('PUSH_TOKEN payload 를 손실 없이 담는다', () => {
    const payload = {
      token: 'ExponentPushToken[abc]',
      platform: 'ios' as const,
      locale: 'ko-KR',
      timezone: 'Asia/Seoul',
      appVersion: '1.0.0',
    };
    const json = serializeAppMessage({ v: BRIDGE_VERSION, type: 'PUSH_TOKEN', payload });
    expect(JSON.parse(json).payload).toEqual(payload);
  });
});

describe('parseWebMessage (웹 → 앱, CWE-345)', () => {
  it('REQUEST_PUSH_PERMISSION / OPEN_OS_SETTINGS 를 파싱한다', () => {
    expect(
      parseWebMessage(JSON.stringify({ v: 1, type: 'REQUEST_PUSH_PERMISSION', payload: {} })),
    ).toEqual({ v: 1, type: 'REQUEST_PUSH_PERMISSION', payload: {} });
    expect(parseWebMessage(JSON.stringify({ v: 1, type: 'OPEN_OS_SETTINGS', payload: {} }))).toEqual(
      { v: 1, type: 'OPEN_OS_SETTINGS', payload: {} },
    );
  });

  it('LOGIN_PROVIDER — provider 열거 검증 + next 상대경로 위생 처리 (CWE-601)', () => {
    expect(
      parseWebMessage(
        JSON.stringify({ v: 1, type: 'LOGIN_PROVIDER', payload: { provider: 'kakao', next: '/settings' } }),
      ),
    ).toEqual({ v: 1, type: 'LOGIN_PROVIDER', payload: { provider: 'kakao', next: '/settings' } });

    // 외부 URL next → '/' 로 대체
    expect(
      parseWebMessage(
        JSON.stringify({
          v: 1,
          type: 'LOGIN_PROVIDER',
          payload: { provider: 'google', next: 'https://evil.example' },
        }),
      ),
    ).toEqual({ v: 1, type: 'LOGIN_PROVIDER', payload: { provider: 'google', next: '/' } });

    // 열거 외 provider → 무시
    expect(
      parseWebMessage(
        JSON.stringify({ v: 1, type: 'LOGIN_PROVIDER', payload: { provider: 'naver', next: '/' } }),
      ),
    ).toBeNull();
  });

  it('SYNC_REQUEST 를 파싱한다 (BUG-006 — mobile-app 3장 v1 증보)', () => {
    expect(parseWebMessage(JSON.stringify({ v: 1, type: 'SYNC_REQUEST', payload: {} }))).toEqual({
      v: 1,
      type: 'SYNC_REQUEST',
      payload: {},
    });
  });

  it('상위 v·미지 type·규약 위반 입력은 무시(null) — 전방 호환, 에러 금지', () => {
    expect(parseWebMessage(JSON.stringify({ v: 2, type: 'OPEN_OS_SETTINGS', payload: {} }))).toBeNull();
    expect(parseWebMessage(JSON.stringify({ v: 1, type: 'FUTURE', payload: {} }))).toBeNull();
    expect(parseWebMessage(JSON.stringify({ v: 1, type: 'OPEN_OS_SETTINGS' }))).toBeNull();
    expect(parseWebMessage(JSON.stringify({ type: 'OPEN_OS_SETTINGS', payload: {} }))).toBeNull();
    expect(parseWebMessage('not-json')).toBeNull();
    expect(parseWebMessage(42)).toBeNull();
    expect(parseWebMessage(null)).toBeNull();
  });
});
