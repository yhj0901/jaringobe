import { describe, expect, it } from 'vitest';
import { parseAppMessage, BRIDGE_VERSION } from '@/shared/bridge/protocol';

const PUSH_PAYLOAD = {
  token: 'ExponentPushToken[abc]',
  platform: 'ios',
  locale: 'ko-KR',
  timezone: 'Asia/Seoul',
  appVersion: '1.0.0',
};

describe('parseAppMessage (mobile-app 3장 — v1 프로토콜)', () => {
  it('BRIDGE_READY / PERMISSION_STATUS / PUSH_TOKEN JSON 문자열을 파싱한다', () => {
    expect(
      parseAppMessage(
        JSON.stringify({ v: 1, type: 'BRIDGE_READY', payload: { appVersion: '1.0.0', platform: 'android' } }),
      ),
    ).toEqual({ v: 1, type: 'BRIDGE_READY', payload: { appVersion: '1.0.0', platform: 'android' } });

    expect(
      parseAppMessage(JSON.stringify({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'granted' } })),
    ).toEqual({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'granted' } });

    expect(parseAppMessage(JSON.stringify({ v: 1, type: 'PUSH_TOKEN', payload: PUSH_PAYLOAD }))).toEqual({
      v: 1,
      type: 'PUSH_TOKEN',
      payload: PUSH_PAYLOAD,
    });
  });

  it('객체 입력도 허용한다', () => {
    expect(
      parseAppMessage({ v: BRIDGE_VERSION, type: 'PERMISSION_STATUS', payload: { status: 'denied' } }),
    ).toEqual({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'denied' } });
  });

  it('상위 버전(v>1)·미지 type 은 무시(null) — 전방 호환, 에러 금지', () => {
    expect(parseAppMessage(JSON.stringify({ v: 2, type: 'PERMISSION_STATUS', payload: { status: 'granted' } }))).toBeNull();
    expect(parseAppMessage(JSON.stringify({ v: 1, type: 'FUTURE_TYPE', payload: {} }))).toBeNull();
  });

  it('규약 위반 payload 는 무시한다', () => {
    // PUSH_TOKEN: 필수 필드 누락/빈 토큰
    expect(parseAppMessage({ v: 1, type: 'PUSH_TOKEN', payload: { token: '' } })).toBeNull();
    expect(parseAppMessage({ v: 1, type: 'PUSH_TOKEN', payload: { ...PUSH_PAYLOAD, platform: 'web' } })).toBeNull();
    // PERMISSION_STATUS: 열거 외 값
    expect(parseAppMessage({ v: 1, type: 'PERMISSION_STATUS', payload: { status: 'maybe' } })).toBeNull();
    // BRIDGE_READY: platform 누락
    expect(parseAppMessage({ v: 1, type: 'BRIDGE_READY', payload: { appVersion: '1.0.0' } })).toBeNull();
    // payload 자체 부재
    expect(parseAppMessage({ v: 1, type: 'BRIDGE_READY' })).toBeNull();
  });

  it('JSON 아님/객체 아님/버전 부재 입력은 무시한다', () => {
    expect(parseAppMessage('not-json')).toBeNull();
    expect(parseAppMessage(42)).toBeNull();
    expect(parseAppMessage(null)).toBeNull();
    expect(parseAppMessage(JSON.stringify({ type: 'PERMISSION_STATUS', payload: { status: 'granted' } }))).toBeNull();
  });
});
