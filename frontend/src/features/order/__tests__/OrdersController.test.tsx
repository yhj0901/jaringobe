import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { OrdersController } from '@/features/order/OrdersController';
import type { OrderPreviewResponse, OrderResponse } from '@/features/order/types';
import type { StoreConnectionsResponse } from '@/features/store/types';
import type { ApiResult } from '@/shared/api/client';
import { renderWithIntl } from '@/test/renderWithIntl';

const routerMock = { push: vi.fn(), replace: vi.fn() };

const previewMock = vi.fn<() => Promise<ApiResult<OrderPreviewResponse>>>();
const createMock = vi.fn<(body: { store: string }) => Promise<ApiResult<OrderResponse>>>();
const latestMock = vi.fn<() => Promise<ApiResult<OrderResponse>>>();
const storesMock = vi.fn<() => Promise<ApiResult<StoreConnectionsResponse>>>();

vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/orders',
  };
});

vi.mock('@/features/order/api', () => ({
  fetchOrderPreview: () => previewMock(),
  createOrder: (body: { store: string }) => createMock(body),
  fetchLatestOrder: () => latestMock(),
}));

vi.mock('@/features/store/api', () => ({
  fetchStoreConnections: () => storesMock(),
}));

const PREVIEW: OrderPreviewResponse = {
  mealPlanId: 'plan-1',
  storeConnected: true,
  country: 'KR',
  needed: [
    { name: '계란', unit: 'ea', needed: '12', fromFridge: '2', toBuy: '10' },
  ],
  covered: [
    { name: '양파', unit: 'ea', needed: '3', fromFridge: '3', toBuy: '0' },
  ],
  cart: {
    items: [
      {
        ingredient: '계란',
        matched: true,
        title: '신선한 계란 10구',
        price: { amount: '5980.00', currency: 'KRW' },
        mallName: '마켓컬리',
        link: 'https://example.com/egg',
        candidateCount: 12,
      },
    ],
    total: { amount: '5980.00', currency: 'KRW' },
    matchedCount: 1,
    notes: [],
  },
  estimatedTotal: { amount: '5980.00', currency: 'KRW' },
  notes: [],
};

const EMPTY_NEEDED: OrderPreviewResponse = {
  ...PREVIEW,
  needed: [],
  cart: { items: [], total: { amount: '0.00', currency: 'KRW' }, matchedCount: 0, notes: [] },
  estimatedTotal: { amount: '0.00', currency: 'KRW' },
};

const ORDER: OrderResponse = {
  id: 'ord-1',
  store: 'kurly',
  status: 'confirmed',
  frequency: 'weekly',
  nextSuggestedAt: '2026-08-22T08:15:00Z',
  estimatedTotal: { amount: '5980.00', currency: 'KRW' },
  confirmedAt: '2026-08-15T08:15:00Z',
  simulation: true,
  items: [
    {
      name: '계란',
      quantity: '10',
      unit: 'ea',
      lineType: 'needed',
      matched: true,
      title: '신선한 계란 10구',
      unitPrice: { amount: '5980.00', currency: 'KRW' },
    },
    {
      name: '양파',
      quantity: '3',
      unit: 'ea',
      lineType: 'covered',
      matched: false,
      title: null,
      unitPrice: null,
    },
  ],
};

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function fail(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

beforeEach(() => {
  vi.clearAllMocks();
  storesMock.mockResolvedValue(
    ok({
      connections: [
        { store: 'kurly', status: 'connected', connectedAt: '2026-08-01T00:00:00Z' },
        { store: 'coupang', status: 'disconnected', connectedAt: null },
      ],
    }),
  );
  latestMock.mockResolvedValue(fail(404, 'ORDER_NOT_FOUND'));
  previewMock.mockResolvedValue(ok(PREVIEW));
  createMock.mockResolvedValue(ok(ORDER, 201));
});

describe('OrdersController 리뷰 (ui-design 13장)', () => {
  it('needed 가 비면 확정 버튼 비활성 + "살 재료가 없어요" + 시뮬레이션 고지', async () => {
    previewMock.mockResolvedValue(ok(EMPTY_NEEDED));
    renderWithIntl(<OrdersController />);

    await waitFor(() => {
      expect(screen.getByText('살 재료가 없어요')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeDisabled();
    expect(screen.getByText('연동 표시 기준 시뮬레이션 (실결제 아님)')).toBeInTheDocument();
    expect(screen.getByText('냉장고가 충당')).toBeInTheDocument();
    expect(screen.getByText('양파')).toBeInTheDocument();
    expect(createMock).not.toHaveBeenCalled();
  });

  it('needed 가 있으면 시뮬레이션 고지 + 추정 합계 + 확정 가능', async () => {
    renderWithIntl(<OrdersController />);

    await waitFor(() => {
      expect(screen.getByText('살 재료')).toBeInTheDocument();
    });
    expect(screen.getByText('계란')).toBeInTheDocument();
    expect(screen.getByText('신선한 계란 10구')).toBeInTheDocument();
    expect(screen.getByText('연동 표시 기준 시뮬레이션 (실결제 아님)')).toBeInTheDocument();
    expect(screen.getByText('네이버 쇼핑(컬리) 검색 기준')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
  });

  it('확정 성공 → 냉장고에 담겼어요 + 다음 제안일 + 시뮬레이션 배지', async () => {
    renderWithIntl(<OrdersController />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: '장바구니 확정' }));

    await waitFor(() => {
      expect(screen.getByText('냉장고에 담겼어요')).toBeInTheDocument();
    });
    expect(screen.getByText('시뮬레이션 확정')).toBeInTheDocument();
    expect(screen.getByText('연동 표시 기준 시뮬레이션 (실결제 아님)')).toBeInTheDocument();
    expect(screen.getByText(/다음 주문 제안일/)).toBeInTheDocument();
    expect(createMock).toHaveBeenCalledWith({ store: 'kurly' });
  });

  it('스토어 미연동 → 배너 + 설정 CTA, 확정 비활성', async () => {
    storesMock.mockResolvedValue(
      ok({
        connections: [
          { store: 'kurly', status: 'disconnected', connectedAt: null },
        ],
      }),
    );
    renderWithIntl(<OrdersController />);

    await waitFor(() => {
      expect(screen.getByText('연동된 스토어가 없어요')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '설정에서 연동하기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/settings');
  });

  it('식단 없음 → 빈 상태 + 홈 CTA', async () => {
    previewMock.mockResolvedValue(fail(404, 'MEALPLAN_NOT_FOUND'));
    renderWithIntl(<OrdersController />);

    await waitFor(() => {
      expect(screen.getByText('먼저 식단을 만들어 주세요')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: '홈으로 가기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/');
  });

  it('이미 확정한 주문이 있으면 재확정 경고를 보여 주고 확정은 허용', async () => {
    latestMock.mockResolvedValue(ok(ORDER));
    renderWithIntl(<OrdersController />);

    await waitFor(() => {
      expect(
        screen.getByText('이미 확정한 주문이 있으면 냉장고 재고가 늘어납니다'),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
  });

  it('en: simulation copy is not a real charge', async () => {
    previewMock.mockResolvedValue(ok(EMPTY_NEEDED));
    renderWithIntl(<OrdersController />, 'en');

    await waitFor(() => {
      expect(
        screen.getByText('Simulation based on linked stores (not a real charge)'),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Confirm cart' })).toBeDisabled();
    expect(screen.getByText('Nothing to buy')).toBeInTheDocument();
  });

  it('401 → /login?next=/orders', async () => {
    previewMock.mockResolvedValue(fail(401, 'AUTH_REQUIRED'));
    storesMock.mockResolvedValue(fail(401, 'AUTH_REQUIRED'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith('/login?next=/orders');
    });
  });

  it('preview 실패 → 로드 에러 + 다시 시도', async () => {
    previewMock.mockResolvedValueOnce(fail(500, 'UNKNOWN'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => {
      expect(screen.getByText(/장보기 목록을 불러오지 못했어요/)).toBeInTheDocument();
    });
    previewMock.mockResolvedValue(ok(PREVIEW));
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
    });
  });

  it('확정 429 → 에러 배너, 라인 재전송 없음', async () => {
    createMock.mockResolvedValue(fail(429, 'RATE_LIMITED'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: '장바구니 확정' }));
    await waitFor(() => {
      expect(screen.getByText(/요청이 많아 잠시 쉬어가는 중/)).toBeInTheDocument();
    });
    expect(createMock).toHaveBeenCalledWith({ store: 'kurly' });
  });
});
