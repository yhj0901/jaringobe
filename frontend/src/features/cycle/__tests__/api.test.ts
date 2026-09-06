import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchCycle, postCycleSkip, putCycleSettings } from '@/features/cycle/api';

function mockFetch() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ stage: 'idle' }),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe('cycle API (api-spec 9장 v1.8)', () => {
  it('GET /cycle', async () => {
    const fetchMock = mockFetch();
    await fetchCycle();
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/cycle');
  });

  it('PUT /cycle/settings 는 부분 갱신 body만 전달한다', async () => {
    const fetchMock = mockFetch();
    await putCycleSettings({ frequency: 'biweekly', anchorWeekday: 2 });
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/cycle/settings');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({ frequency: 'biweekly', anchorWeekday: 2 });
  });

  it('POST /cycle/skip 은 body 없이 호출한다', async () => {
    const fetchMock = mockFetch();
    await postCycleSkip();
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/cycle/skip');
    expect(init.method).toBe('POST');
    expect(init.body).toBeUndefined();
  });
});
