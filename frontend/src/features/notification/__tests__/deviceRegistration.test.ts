import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  flushPendingDeviceToken,
  hasPendingDeviceToken,
  registerPushToken,
  resetDeviceRegistration,
  toDeviceRegisterRequest,
} from '@/features/notification/deviceRegistration';
import { registerDevice } from '@/features/notification/api';
import type { ApiResult } from '@/shared/api/client';

vi.mock('@/features/notification/api', () => ({ registerDevice: vi.fn() }));

const registerMock = vi.mocked(registerDevice);

const PAYLOAD = {
  token: 'ExponentPushToken[abc]',
  platform: 'ios' as const,
  locale: 'ko-KR',
  timezone: 'Asia/Seoul',
  appVersion: '1.0.0',
};

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function err(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

beforeEach(() => {
  vi.clearAllMocks();
  resetDeviceRegistration();
});

describe('toDeviceRegisterRequest — locale 정규화 (api-spec 6-A-1: ko|en)', () => {
  it('ko-KR → ko, 그 외 → en', () => {
    expect(toDeviceRegisterRequest(PAYLOAD).locale).toBe('ko');
    expect(toDeviceRegisterRequest({ ...PAYLOAD, locale: 'en-US' }).locale).toBe('en');
    expect(toDeviceRegisterRequest({ ...PAYLOAD, locale: 'fr' }).locale).toBe('en');
  });
});

describe('registerPushToken — 로그인 상태면 즉시 등록, 401 이면 메모리 보류 (ui-design 12장)', () => {
  it('로그인 상태 → PUT 성공, 보류 없음', async () => {
    registerMock.mockResolvedValue(ok({ id: 'dev-1' }));
    const done = await registerPushToken(PAYLOAD);
    expect(done).toBe(true);
    expect(registerMock).toHaveBeenCalledWith({
      token: PAYLOAD.token,
      platform: 'ios',
      locale: 'ko',
      timezone: 'Asia/Seoul',
      appVersion: '1.0.0',
    });
    expect(hasPendingDeviceToken()).toBe(false);
  });

  it('401(미로그인) → 보류 → flushPendingDeviceToken 으로 등록', async () => {
    registerMock.mockResolvedValueOnce(err(401, 'AUTH_REQUIRED'));
    const done = await registerPushToken(PAYLOAD);
    expect(done).toBe(false);
    expect(hasPendingDeviceToken()).toBe(true);

    registerMock.mockResolvedValueOnce(ok({ id: 'dev-1' }));
    await flushPendingDeviceToken();
    expect(registerMock).toHaveBeenCalledTimes(2);
    expect(hasPendingDeviceToken()).toBe(false);
  });

  it('401 이외 실패는 보류하지 않는다 (일시 오류 — 다음 앱 실행 시 재전송)', async () => {
    registerMock.mockResolvedValue(err(500, 'UNKNOWN'));
    await registerPushToken(PAYLOAD);
    expect(hasPendingDeviceToken()).toBe(false);
  });

  it('flush 시에도 401 이면 보류 유지, 보류 없으면 no-op', async () => {
    registerMock.mockResolvedValue(err(401, 'AUTH_REQUIRED'));
    await registerPushToken(PAYLOAD);
    await flushPendingDeviceToken();
    expect(hasPendingDeviceToken()).toBe(true);

    resetDeviceRegistration();
    registerMock.mockClear();
    await flushPendingDeviceToken();
    expect(registerMock).not.toHaveBeenCalled();
  });
});
