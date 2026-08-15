import { describe, expect, it } from 'vitest';
import { pickFirstConnectedStore } from '@/features/order/pickStore';
import type { StoreConnection } from '@/features/store/types';

const rows = (items: Array<[StoreConnection['store'], StoreConnection['status']]>): StoreConnection[] =>
  items.map(([store, status]) => ({
    store,
    status,
    connectedAt: status === 'connected' ? '2026-08-01T00:00:00Z' : null,
  }));

describe('pickFirstConnectedStore', () => {
  it('KR 세트 순서에서 첫 connected (쿠팡이 응답 앞에 있어도 컬리가 우선)', () => {
    expect(
      pickFirstConnectedStore(
        'KR',
        rows([
          ['coupang', 'connected'],
          ['kurly', 'connected'],
        ]),
      ),
    ).toBe('kurly');
  });

  it('연동 0개 → null', () => {
    expect(pickFirstConnectedStore('KR', rows([['kurly', 'disconnected']]))).toBeNull();
  });

  it('US 세트는 walmart 가 우선', () => {
    expect(
      pickFirstConnectedStore(
        'US',
        rows([
          ['instacart', 'connected'],
          ['walmart', 'connected'],
        ]),
      ),
    ).toBe('walmart');
  });
});
