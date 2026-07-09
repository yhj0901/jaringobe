import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchStoreConnections, putStoreConnection } from '@/features/store/api';
import { postLogout } from '@/features/auth/logout';

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

describe('store 연동 API 클라이언트 (api-spec 6장 v1.3)', () => {
  it('fetchStoreConnections → GET /api/v1/stores/connections', async () => {
    const fetchMock = mockFetch(200, {
      connections: [{ store: 'kurly', status: 'connected', connectedAt: '2026-07-10T00:00:00Z' }],
    });
    const result = await fetchStoreConnections();

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/stores/connections');
    if (result.ok) expect(result.data.connections[0]?.store).toBe('kurly');
  });

  it('putStoreConnection → PUT /api/v1/stores/connections/{store} + connected body', async () => {
    const fetchMock = mockFetch(200, {});
    const result = await putStoreConnection('coupang', true);

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/stores/connections/coupang');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({ connected: true });
  });

  it('putStoreConnection 실패 → 에러 코드 전달 (STORE_NOT_SUPPORTED)', async () => {
    mockFetch(404, { detail: { code: 'STORE_NOT_SUPPORTED', message: 'nope' } });
    const result = await putStoreConnection('naver', false);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('STORE_NOT_SUPPORTED');
  });
});

describe('postLogout (api-spec 1-4)', () => {
  it('POST /api/v1/auth/logout — 204 성공', async () => {
    const fetchMock = mockFetch(204);
    const result = await postLogout();

    expect(result.ok).toBe(true);
    expect(result.status).toBe(204);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/logout');
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).method).toBe('POST');
  });

  it('401 → 실패 결과 전달', async () => {
    mockFetch(401, { detail: { code: 'AUTH_REQUIRED', message: 'no' } });
    const result = await postLogout();
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.status).toBe(401);
  });
});
