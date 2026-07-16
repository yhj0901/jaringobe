import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createMealPlan,
  fetchLatestMealPlan,
  fetchMealPlan,
  regenerateMealPlan,
  setMealCompletion,
} from '@/features/mealplan/api';

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
});

describe('mealplan API 클라이언트 (api-spec 3장 v1.5)', () => {
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

  it('fetchMealPlan → GET /api/v1/mealplans/{id} (폴링 겸용, api-spec 3-3)', async () => {
    const fetchMock = mockFetch(200, { id: 'plan-1', status: 'processing' });
    const result = await fetchMealPlan('plan-1');
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans/plan-1');
  });

  it('createMealPlan → POST /api/v1/mealplans, 202 Accepted 수신 (v1.5 비동기)', async () => {
    const fetchMock = mockFetch(202, { id: 'plan-1', status: 'processing' });
    const result = await createMealPlan(CREATE_BODY);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.status).toBe(202);
      expect(result.data).toEqual({ id: 'plan-1', status: 'processing' });
    }

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual(CREATE_BODY);
    // v1.5: 90초 클라이언트 타임아웃 제거 — abort signal 미사용 (ui-design 12장)
    expect(init.signal).toBeUndefined();
  });

  it('regenerateMealPlan → POST /mealplans/{id}/regenerate scope=all, 202 (FR-209)', async () => {
    const fetchMock = mockFetch(202, { id: 'plan-1', status: 'processing' });
    const result = await regenerateMealPlan('plan-1');
    expect(result.ok).toBe(true);

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans/plan-1/regenerate');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ scope: 'all' });
  });

  it('setMealCompletion → PUT /mealplans/{planId}/meals/{mealId}/completion (FR-501)', async () => {
    const fetchMock = mockFetch(200, { id: 'm1', completedAt: '2026-07-14T09:00:00Z' });
    const result = await setMealCompletion('plan-1', 'm1', true);
    expect(result.ok).toBe(true);

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/mealplans/plan-1/meals/m1/completion');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({ completed: true });
  });

  it('createMealPlan 409 MEALPLAN_GENERATING → 코드 전달 (중복 생성 방지)', async () => {
    mockFetch(409, { detail: { code: 'MEALPLAN_GENERATING', message: 'in progress' } });
    const result = await createMealPlan(CREATE_BODY);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.code).toBe('MEALPLAN_GENERATING');
    }
  });
});
