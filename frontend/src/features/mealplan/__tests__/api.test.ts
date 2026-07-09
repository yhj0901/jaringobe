import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createMealPlan,
  fetchLatestMealPlan,
  regenerateMealPlan,
} from '@/features/mealplan/api';
import { MEALPLAN_CREATE_TIMEOUT_MS } from '@/features/mealplan/constants';
import { NETWORK_ERROR_CODE } from '@/shared/api/client';

const CREATE_BODY = { days: 7, mealsPerDay: 3, allergies: ['땅콩'], preferences: ['한식'] };

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
  vi.useRealTimers();
});

describe('mealplan API 클라이언트 (api-spec 3장)', () => {
  it('fetchLatestMealPlan → GET /api/v1/mealplans/latest', async () => {
    const fetchMock = mockFetch(200, { id: 'plan-1' });
    const result = await fetchLatestMealPlan();
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans/latest');
  });

  it('fetchLatestMealPlan 404 → MEALPLAN_NOT_FOUND 코드 전달', async () => {
    mockFetch(404, { detail: { code: 'MEALPLAN_NOT_FOUND', message: 'none' } });
    const result = await fetchLatestMealPlan();
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('MEALPLAN_NOT_FOUND');
  });

  it('createMealPlan → POST /api/v1/mealplans + 팀원 스키마 그대로 직렬화', async () => {
    const fetchMock = mockFetch(201, { id: 'plan-1' });
    const result = await createMealPlan(CREATE_BODY);
    expect(result.ok).toBe(true);

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual(CREATE_BODY);
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it('regenerateMealPlan → POST /mealplans/{id}/regenerate scope=all (FR-209)', async () => {
    const fetchMock = mockFetch(200, { id: 'plan-1' });
    await regenerateMealPlan('plan-1');

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans/plan-1/regenerate');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ scope: 'all' });
  });

  it('createMealPlan 은 90초 후 클라이언트 타임아웃(abort) 된다', async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError')),
            );
          }),
      ),
    );

    const pending = createMealPlan(CREATE_BODY);
    vi.advanceTimersByTime(MEALPLAN_CREATE_TIMEOUT_MS);
    const result = await pending;

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe(NETWORK_ERROR_CODE);
      expect(result.status).toBe(0);
    }
  });
});
