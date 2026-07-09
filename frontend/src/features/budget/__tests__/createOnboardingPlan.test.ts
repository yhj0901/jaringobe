import { afterEach, describe, expect, it, vi } from 'vitest';
import { createOnboardingPlan } from '@/features/budget/createOnboardingPlan';
import type { GuestPlan } from '@/features/guest/store';

const PLAN: GuestPlan = {
  householdSize: 2,
  amount: '500000',
  currency: 'KRW',
  mealDirection: 'health',
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

describe('createOnboardingPlan (FR-207, api-spec 2-1)', () => {
  it("201 → created + 응답 plan 반환, source='onboarding' 으로 POST 한다", async () => {
    const response = {
      id: 'b1',
      householdSize: 2,
      budget: { amount: '500000.00', currency: 'KRW' },
      mealDirection: 'health',
      source: 'onboarding',
      createdAt: '2026-07-09T04:00:00Z',
    };
    const fetchMock = mockFetch(201, response);

    const result = await createOnboardingPlan(PLAN);
    expect(result).toEqual({ kind: 'created', plan: response });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/budget/plans',
      expect.objectContaining({ method: 'POST' }),
    );
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({
      householdSize: 2,
      budget: { amount: '500000', currency: 'KRW' },
      mealDirection: 'health',
      source: 'onboarding',
    });
  });

  it('409 → already-exists / 422 → invalid / 그 외 → error', async () => {
    mockFetch(409, { detail: { code: 'BUDGET_PLAN_EXISTS', message: 'exists' } });
    expect(await createOnboardingPlan(PLAN)).toEqual({ kind: 'already-exists' });

    mockFetch(422, { detail: { code: 'VALIDATION_ERROR', message: 'invalid' } });
    expect(await createOnboardingPlan(PLAN)).toEqual({ kind: 'invalid' });

    mockFetch(500, {});
    expect(await createOnboardingPlan(PLAN)).toEqual({ kind: 'error' });

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    expect(await createOnboardingPlan(PLAN)).toEqual({ kind: 'error' });
  });
});
