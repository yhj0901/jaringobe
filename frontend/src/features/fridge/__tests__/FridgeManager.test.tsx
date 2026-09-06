import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FridgeManager } from '@/features/fridge/FridgeManager';
import type { FridgeItem } from '@/features/fridge/api';
import type { CycleState } from '@/features/cycle/types';
import type { OrderResponse } from '@/features/order/types';
import type { ApiResult } from '@/shared/api/client';
import { renderWithIntl } from '@/test/renderWithIntl';

const listMock = vi.fn<() => Promise<ApiResult<FridgeItem[]>>>();
const addMock = vi.fn<() => Promise<ApiResult<FridgeItem[]>>>();
const deleteMock = vi.fn<() => Promise<ApiResult<void>>>();
const updateMock = vi.fn<() => Promise<ApiResult<FridgeItem>>>();
const latestMock = vi.fn<() => Promise<ApiResult<OrderResponse>>>();
const cycleMock = vi.fn<() => Promise<ApiResult<CycleState>>>();
const deliveryMock = vi.fn<() => Promise<ApiResult<OrderResponse>>>();

vi.mock('@/features/fridge/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/fridge/api')>();
  return {
    ...actual,
    listFridge: () => listMock(),
    addFridgeItems: () => addMock(),
    deleteFridgeItem: () => deleteMock(),
    updateFridgeQuantity: () => updateMock(),
  };
});
vi.mock('@/features/order/api', () => ({
  fetchLatestOrder: () => latestMock(),
  confirmOrderDelivery: () => deliveryMock(),
}));
vi.mock('@/features/cycle/api', () => ({ fetchCycle: () => cycleMock() }));

const ITEM: FridgeItem = {
  id: 'f1',
  name: '두부',
  quantity: '1',
  unit: 'ea',
  expiresAt: new Date().toISOString().slice(0, 10),
  source: 'delivery',
  createdAt: '2026-09-01T00:00:00Z',
};

const ORDER: OrderResponse = {
  id: 'o1',
  store: 'kurly',
  status: 'confirmed',
  frequency: 'weekly',
  nextSuggestedAt: '2026-09-13T00:00:00Z',
  estimatedTotal: { amount: '5000.00', currency: 'KRW' },
  confirmedAt: '2026-09-05T00:00:00Z',
  simulation: true,
  items: [],
  cycleStart: '2026-09-06',
  deliveryEta: '2026-09-07T00:00:00Z',
  inboundAt: '2026-09-07T00:00:00Z',
  deliveryState: 'delivered',
  deliveryConfirmAttempts: 0,
  autoConfirmed: false,
  autoConfirmAt: null,
  blockedReason: null,
};

const CYCLE: CycleState = {
  enabled: true,
  frequency: 'weekly',
  anchorWeekday: 0,
  timezone: 'Asia/Seoul',
  autoConfirm: true,
  cycleStart: '2026-09-06',
  cycleDays: 7,
  stage: 'delivered',
  nextRunAt: null,
  skippedCycleStart: null,
  weeklyLimit: null,
  mealPlan: null,
  draftOrder: null,
  currentOrder: null,
  simulation: true,
};

const ok = <T,>(data: T): ApiResult<T> => ({ ok: true, status: 200, data });
const fail = (status: number, code: string): ApiResult<never> => ({
  ok: false,
  status,
  code,
  i18nKey: 'common.error.fallback',
});

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  listMock.mockResolvedValue(ok([ITEM]));
  addMock.mockResolvedValue(ok([ITEM]));
  deleteMock.mockResolvedValue({ ok: true, status: 204, data: undefined });
  updateMock.mockResolvedValue(ok({ ...ITEM, quantity: '2' }));
  latestMock.mockResolvedValue(fail(404, 'ORDER_NOT_FOUND'));
  cycleMock.mockResolvedValue(ok({ ...CYCLE, stage: 'idle' }));
  deliveryMock.mockResolvedValue(ok(ORDER));
});

describe('FridgeManager 배송 보정과 수동 재고', () => {
  it('목록·임박 안내·추가·삭제 흐름을 제공한다', async () => {
    renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByText('두부')).toBeInTheDocument());
    expect(screen.getByText(/임박 재료는 다음 식단/)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('재료명 (예: 두부)'), {
      target: { value: '계란' },
    });
    fireEvent.change(screen.getByPlaceholderText('수량'), { target: { value: '3' } });
    fireEvent.submit(screen.getByRole('button', { name: '냉장고에 추가' }).closest('form')!);
    await waitFor(() => expect(addMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole('button', { name: '두부 삭제' }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledTimes(1));
  });

  it('배송 자동등록 시트에서 수량 수정 진입 후 PATCH 결과를 반영한다', async () => {
    latestMock.mockResolvedValue(ok(ORDER));
    cycleMock.mockResolvedValue(ok(CYCLE));
    renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByText('받으셨나요?')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '수량 수정' }));
    const input = screen.getByRole('textbox', { name: '두부 수량 수정' });
    fireEvent.change(input, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '수정' }));
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    expect(screen.getByText('2ea')).toBeInTheDocument();
  });

  it('맞아요는 delivery=true 처리 후 같은 주문 시트를 로컬에서 닫는다', async () => {
    latestMock.mockResolvedValue(ok(ORDER));
    cycleMock.mockResolvedValue(ok(CYCLE));
    deliveryMock.mockResolvedValue(ok(ORDER));
    renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByRole('button', { name: '맞아요' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '맞아요' }));
    await waitFor(() => expect(deliveryMock).toHaveBeenCalledTimes(1));
    expect(window.localStorage.getItem('fridge.delivery.confirmed:o1')).toBe('1');
    await waitFor(() => expect(screen.queryByRole('button', { name: '맞아요' })).not.toBeInTheDocument());
  });

  it('아직 안 왔어요와 unknown 배너를 구분한다', async () => {
    latestMock.mockResolvedValue(ok(ORDER));
    cycleMock.mockResolvedValue(ok(CYCLE));
    deliveryMock.mockResolvedValue(
      ok({ ...ORDER, inboundAt: null, deliveryState: 'pending', deliveryConfirmAttempts: 1 }),
    );
    const first = renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByRole('button', { name: '아직 안 왔어요' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '아직 안 왔어요' }));
    await waitFor(() => expect(deliveryMock).toHaveBeenCalledTimes(1));
    first.unmount();

    latestMock.mockResolvedValue(ok({ ...ORDER, deliveryState: 'unknown' }));
    renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByText('받으면 알려주세요')).toBeInTheDocument());
    expect(screen.queryByText('받으셨나요?')).not.toBeInTheDocument();
  });

  it('401·오류·빈 목록 상태를 구분한다', async () => {
    listMock.mockResolvedValueOnce(fail(401, 'AUTH_REQUIRED'));
    const first = renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByText('로그인이 필요해요.')).toBeInTheDocument());
    first.unmount();

    listMock.mockResolvedValueOnce(fail(500, 'UNKNOWN'));
    const second = renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByText('재고를 불러오지 못했어요.')).toBeInTheDocument());
    second.unmount();

    listMock.mockResolvedValueOnce(ok([]));
    renderWithIntl(<FridgeManager />);
    await waitFor(() => expect(screen.getByText(/냉장고가 비어 있어요/)).toBeInTheDocument());
  });
});
