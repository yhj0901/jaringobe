import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  deleteDevice,
  fetchNotificationSettings,
  putNotificationSettings,
  registerDevice,
} from '@/features/notification/api';

function mockFetch(status: number, jsonBody: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(jsonBody),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('notification API 클라이언트 (api-spec 6-A v1.5)', () => {
  it('registerDevice → PUT /api/v1/notifications/devices (upsert)', async () => {
    const fetchMock = mockFetch(200, { id: 'dev-1' });
    const request = {
      token: 'ExponentPushToken[abc]',
      platform: 'ios' as const,
      locale: 'ko' as const,
      timezone: 'Asia/Seoul',
      appVersion: '1.0.0',
    };
    const result = await registerDevice(request);

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/notifications/devices');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual(request);
  });

  it('deleteDevice → DELETE /devices/{token}, 토큰은 URL 인코딩 (api-spec 6-A-2)', async () => {
    const fetchMock = mockFetch(204);
    const result = await deleteDevice('ExponentPushToken[a/b]');
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/v1/notifications/devices/${encodeURIComponent('ExponentPushToken[a/b]')}`,
    );
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).method).toBe('DELETE');
  });

  it('fetchNotificationSettings → GET /notifications/settings', async () => {
    const fetchMock = mockFetch(200, { settings: [] });
    const result = await fetchNotificationSettings();
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/notifications/settings');
  });

  it('putNotificationSettings → PUT — 보낸 type 만 부분 갱신 (api-spec 6-A-4)', async () => {
    const fetchMock = mockFetch(200, { settings: [] });
    await putNotificationSettings([{ type: 'meal_reminder_dinner', enabled: true, localTime: '19:00' }]);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({
      settings: [{ type: 'meal_reminder_dinner', enabled: true, localTime: '19:00' }],
    });
  });
});
