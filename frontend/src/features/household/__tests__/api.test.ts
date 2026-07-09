import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchBudgetPlan,
  fetchHousehold,
  putBudgetPlan,
  putHouseholdMembers,
} from '@/features/household/api';
import type { BudgetPlanUpsertRequest } from '@/features/household/types';

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

describe('household API 클라이언트 (api-spec 4장·5장 v1.2)', () => {
  it('putHouseholdMembers → PUT /api/v1/households/me + members 배열 직렬화', async () => {
    const fetchMock = mockFetch(200, { members: [], size: 2 });
    const members = [
      { memberType: 'adult_m' as const, age: 35 },
      { memberType: 'toddler' as const, age: 4 },
    ];
    const result = await putHouseholdMembers(members);

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/households/me');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual({ members });
  });

  it('putHouseholdMembers 실패 → 에러 코드 전달', async () => {
    mockFetch(422, { detail: { code: 'VALIDATION_ERROR', message: 'bad' } });
    const result = await putHouseholdMembers([{ memberType: 'adult_m', age: 35 }]);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('VALIDATION_ERROR');
  });

  it('fetchHousehold → GET /api/v1/households/me (api-spec 4-2)', async () => {
    const fetchMock = mockFetch(200, {
      members: [{ memberType: 'adult_m', age: 35 }],
      size: 1,
    });
    const result = await fetchHousehold();

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/households/me');
    if (result.ok) expect(result.data.size).toBe(1);
  });

  it('fetchHousehold 404 → HOUSEHOLD_NOT_FOUND 코드 전달', async () => {
    mockFetch(404, { detail: { code: 'HOUSEHOLD_NOT_FOUND', message: 'none' } });
    const result = await fetchHousehold();
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('HOUSEHOLD_NOT_FOUND');
  });

  it('fetchBudgetPlan → GET /api/v1/budget/plans — locked·cuisines 포함 (api-spec 2-2 v1.3.1)', async () => {
    const fetchMock = mockFetch(200, {
      id: 'b1',
      householdSize: 2,
      budget: { amount: '420000.00', currency: 'KRW' },
      mealDirection: 'hearty',
      source: 'onboarding',
      createdAt: '2026-07-09T00:00:00Z',
      locked: true,
      cuisines: ['japanese'],
    });
    const result = await fetchBudgetPlan();

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/budget/plans');
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit | undefined)?.method).toBeUndefined();
    if (result.ok) {
      expect(result.data.locked).toBe(true);
      expect(result.data.cuisines).toEqual(['japanese']);
    }
  });

  it('fetchBudgetPlan 404 → BUDGET_PLAN_NOT_FOUND 코드 전달', async () => {
    mockFetch(404, { detail: { code: 'BUDGET_PLAN_NOT_FOUND', message: 'none' } });
    const result = await fetchBudgetPlan();
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('BUDGET_PLAN_NOT_FOUND');
  });

  it('putBudgetPlan → PUT /api/v1/budget/plans + locked·cuisines 포함 직렬화 (api-spec 5-1)', async () => {
    const fetchMock = mockFetch(201, { id: 'b1' });
    const body: BudgetPlanUpsertRequest = {
      householdSize: 5,
      budget: { amount: '450000', currency: 'KRW' },
      mealDirection: 'health',
      locked: true,
      cuisines: ['korean', 'japanese'],
    };
    const result = await putBudgetPlan(body);

    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/budget/plans');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect(JSON.parse(init.body as string)).toEqual(body);
  });
});
