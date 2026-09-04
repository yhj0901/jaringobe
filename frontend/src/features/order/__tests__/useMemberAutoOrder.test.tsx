import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useMemberAutoOrder } from '@/features/order/useMemberAutoOrder';
import { IntlWrapper } from '@/test/renderWithIntl';
import type { ApiResult } from '@/shared/api/client';
import type { OrderPreviewResponse } from '@/features/order/types';
import type { StoreConnectionsResponse } from '@/features/store/types';

const previewMock = vi.fn<() => Promise<ApiResult<OrderPreviewResponse>>>();
const storesMock = vi.fn<() => Promise<ApiResult<StoreConnectionsResponse>>>();

vi.mock('@/features/order/api', () => ({
  fetchOrderPreview: () => previewMock(),
}));
vi.mock('@/features/store/api', () => ({
  fetchStoreConnections: () => storesMock(),
}));

function ok<T>(data: T): ApiResult<T> {
  return { ok: true, status: 200, data };
}
function fail(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe('useMemberAutoOrder', () => {
  it('연동 0개 → active=false', async () => {
    storesMock.mockResolvedValue(
      ok({ connections: [{ store: 'kurly', status: 'disconnected', connectedAt: null }] }),
    );
    previewMock.mockResolvedValue(fail(404, 'MEALPLAN_NOT_FOUND'));

    const { result } = renderHook(() => useMemberAutoOrder(), { wrapper: IntlWrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.active).toBe(false);
    expect(result.current.stores).toEqual([]);
    expect(result.current.recommendedItems).toEqual([]);
  });

  it('연동 + needed 8개 → 칩 6개 + moreCount 2, 스토어 i18n 이름', async () => {
    storesMock.mockResolvedValue(
      ok({
        connections: [
          { store: 'kurly', status: 'connected', connectedAt: '2026-08-01T00:00:00Z' },
        ],
      }),
    );
    const names = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
    previewMock.mockResolvedValue(
      ok({
        mealPlanId: 'p',
        storeConnected: true,
        country: 'KR',
        needed: names.map((name) => ({
          name,
          unit: 'ea',
          needed: '1',
          fromFridge: '0',
          toBuy: '1',
        })),
        covered: [],
        cart: { items: [], total: { amount: '0.00', currency: 'KRW' }, matchedCount: 0, notes: [] },
        estimatedTotal: { amount: '0.00', currency: 'KRW' },
        notes: [],
      }),
    );

    const { result } = renderHook(() => useMemberAutoOrder(), { wrapper: IntlWrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.active).toBe(true);
    expect(result.current.stores).toEqual([{ id: 'kurly', name: '마켓컬리' }]);
    expect(result.current.recommendedItems).toEqual(['a', 'b', 'c', 'd', 'e', 'f']);
    expect(result.current.moreCount).toBe(2);
  });
});
