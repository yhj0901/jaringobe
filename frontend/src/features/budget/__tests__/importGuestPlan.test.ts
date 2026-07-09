import { afterEach, describe, expect, it, vi } from 'vitest';
import { importGuestPlan } from '@/features/budget/importGuestPlan';
import type { GuestPlan } from '@/features/guest/store';

const PLAN: GuestPlan = {
  householdSize: 4,
  amount: '700000',
  currency: 'KRW',
  mealDirection: 'kids',
};

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

describe('importGuestPlan (FR-108, api-spec 2-1)', () => {
  it('201 → created, api-spec 스키마로 POST 한다', async () => {
    const fetchMock = mockFetch(201, { id: 'p1' });
    const result = await importGuestPlan(PLAN);
    expect(result).toBe('created');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/budget/plans',
      expect.objectContaining({ method: 'POST' }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      householdSize: 4,
      budget: { amount: '700000', currency: 'KRW' },
      mealDirection: 'kids',
      source: 'guest',
    });
  });

  it('409 BUDGET_PLAN_EXISTS → already-exists', async () => {
    mockFetch(409, { detail: { code: 'BUDGET_PLAN_EXISTS', message: 'exists' } });
    expect(await importGuestPlan(PLAN)).toBe('already-exists');
  });

  it('422 VALIDATION_ERROR → invalid (변조 의심)', async () => {
    mockFetch(422, { detail: { code: 'VALIDATION_ERROR', message: 'invalid' } });
    expect(await importGuestPlan(PLAN)).toBe('invalid');
  });

  it('그 외 상태/네트워크 오류 → error', async () => {
    mockFetch(500, { detail: { code: 'INTERNAL', message: 'boom' } });
    expect(await importGuestPlan(PLAN)).toBe('error');

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')));
    expect(await importGuestPlan(PLAN)).toBe('error');
  });
});
