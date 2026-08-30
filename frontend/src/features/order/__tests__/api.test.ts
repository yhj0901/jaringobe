import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  approveOrder,
  cancelOrder,
  confirmOrderDelivery,
  createOrder,
  fetchLatestOrder,
  fetchOrderPreview,
} from '@/features/order/api';

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

describe('order API 클라이언트 (api-spec 7장)', () => {
  it('fetchOrderPreview → GET /api/v1/orders/preview + credentials', async () => {
    const fetchMock = mockFetch(200, { needed: [], covered: [] });
    const result = await fetchOrderPreview();
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/orders/preview');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.credentials).toBe('same-origin');
  });

  it('createOrder → POST /api/v1/orders body { store } 만 (라인 없음)', async () => {
    const fetchMock = mockFetch(201, { id: 'ord-1', store: 'kurly' });
    const result = await createOrder({ store: 'kurly' });
    expect(result.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/orders');
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ store: 'kurly' });
  });

  it('fetchLatestOrder 404 → ORDER_NOT_FOUND', async () => {
    mockFetch(404, { detail: { code: 'ORDER_NOT_FOUND', message: 'none' } });
    const result = await fetchLatestOrder();
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('ORDER_NOT_FOUND');
  });

  it('createOrder 422 STORE_NOT_CONNECTED', async () => {
    mockFetch(422, { detail: { code: 'STORE_NOT_CONNECTED', message: 'no' } });
    const result = await createOrder({ store: 'kurly' });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.code).toBe('STORE_NOT_CONNECTED');
  });

  it('preview refresh는 명시적으로 ?refresh=true를 붙인다', async () => {
    const fetchMock = mockFetch(200, {});
    await fetchOrderPreview(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/orders/preview?refresh=true');
  });

  it('approve/cancel/delivery 액션은 id를 인코딩하고 계약 body만 보낸다', async () => {
    const fetchMock = mockFetch(200, {});
    await approveOrder('a/b');
    await cancelOrder('a/b');
    await confirmOrderDelivery('a/b', false);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/orders/a%2Fb/approve');
    expect(JSON.parse((fetchMock.mock.calls[0]?.[1] as RequestInit).body as string)).toEqual({});
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/orders/a%2Fb/cancel');
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/orders/a%2Fb/delivery');
    expect(JSON.parse((fetchMock.mock.calls[2]?.[1] as RequestInit).body as string)).toEqual({ received: false });
  });
});
