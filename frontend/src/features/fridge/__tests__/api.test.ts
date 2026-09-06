import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  addFridgeItems,
  daysUntil,
  deleteFridgeItem,
  listFridge,
  updateFridgeQuantity,
} from '@/features/fridge/api';

function mockFetch(status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve([]),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe('fridge API', () => {
  it('목록·추가·삭제 경로와 body를 지킨다', async () => {
    const fetchMock = mockFetch();
    await listFridge();
    await addFridgeItems([{ name: '두부', quantity: '1', unit: 'ea' }]);
    await deleteFridgeItem('a/b');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/fridge');
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/fridge/items');
    expect(JSON.parse((fetchMock.mock.calls[1]?.[1] as RequestInit).body as string)).toEqual({
      items: [{ name: '두부', quantity: '1', unit: 'ea' }],
    });
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/fridge/items/a/b');
  });

  it('PATCH 수량 보정은 id 인코딩과 quantity만 보낸다', async () => {
    const fetchMock = mockFetch();
    await updateFridgeQuantity('a/b', '2.5');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/fridge/items/a%2Fb');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ quantity: '2.5' });
  });

  it('daysUntil은 null과 로컬 달력 날짜 차이를 계산한다', () => {
    expect(daysUntil(null)).toBeNull();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today.getTime() + 86_400_000);
    const iso = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`;
    expect(daysUntil(iso)).toBe(1);
  });
});
