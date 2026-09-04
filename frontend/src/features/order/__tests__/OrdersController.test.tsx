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
const approveMock = vi.fn<(id: string) => Promise<ApiResult<OrderResponse>>>();
const recalculateMock = vi.fn<(id: string) => Promise<ApiResult<OrderResponse>>>();
const cancelMock = vi.fn<(id: string) => Promise<ApiResult<OrderResponse>>>();
const skipMock = vi.fn<() => Promise<ApiResult<unknown>>>();
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
  approveOrder: (id: string) => approveMock(id),
  recalculateOrder: (id: string) => recalculateMock(id),
  cancelOrder: (id: string) => cancelMock(id),
}));

vi.mock('@/features/cycle/api', () => ({
  postCycleSkip: () => skipMock(),
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
  orderId: null,
  status: null,
  autoConfirmAt: null,
  blockedReason: null,
  cycleStart: '2026-08-17',
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
  cycleStart: '2026-08-17',
  deliveryEta: '2026-08-18T08:15:00Z',
  inboundAt: null,
  deliveryState: 'pending',
  deliveryConfirmAttempts: 0,
  autoConfirmed: false,
  autoConfirmAt: null,
  blockedReason: null,
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

const DRAFT: OrderResponse = {
  ...ORDER,
  status: 'draft',
  confirmedAt: null,
  deliveryEta: null,
  autoConfirmAt: '2026-08-16T08:15:00Z',
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
  approveMock.mockResolvedValue(ok(ORDER));
  recalculateMock.mockResolvedValue(ok(DRAFT));
  cancelMock.mockResolvedValue(ok({ ...ORDER, status: 'cancelled' }));
  skipMock.mockResolvedValue(ok({}));
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

  it('명시적 확정 성공 → confirmed 상태 + 배송 예정 + 시뮬레이션 고지', async () => {
    renderWithIntl(<OrdersController />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: '장바구니 확정' }));

    await waitFor(() => {
      expect(screen.getByText('확정')).toBeInTheDocument();
    });
    expect(screen.getByText('연동 표시 기준 시뮬레이션 (실결제 아님)')).toBeInTheDocument();
    expect(screen.getByText(/도착 예정/)).toBeInTheDocument();
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

  it('최신 주문이 confirmed 면 preview 확정 UI 대신 스냅샷과 취소 CTA를 보여 준다', async () => {
    latestMock.mockResolvedValue(ok(ORDER));
    renderWithIntl(<OrdersController />);

    await waitFor(() => {
      expect(screen.getByText('확정')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '주문 취소' })).toBeEnabled();
  });

  it.each(['cancelled', 'expired'] as const)(
    '이전 사이클의 %s 주문은 현재 preview 리뷰를 막지 않는다',
    async (status) => {
      latestMock.mockResolvedValue(
        ok({
          ...ORDER,
          status,
          cycleStart: '2026-08-10',
          confirmedAt: status === 'expired' ? null : ORDER.confirmedAt,
        }),
      );
      renderWithIntl(<OrdersController />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: '장바구니 확정' })).toBeEnabled();
      });
      expect(screen.queryByText('이번 주문은 취소됐어요')).not.toBeInTheDocument();
      expect(screen.queryByText('승인 시간이 지났어요')).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: '장바구니 확정' }));
      await waitFor(() => expect(createMock).toHaveBeenCalledWith({ store: 'kurly' }));
    },
  );

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

  it('latest 조회 실패 → 로드 에러를 표시한다', async () => {
    latestMock.mockResolvedValue(fail(500, 'UNKNOWN'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => {
      expect(screen.getByText(/장보기 목록을 불러오지 못했어요/)).toBeInTheDocument();
    });
  });

  it('preview 조회 실패여도 저장된 최신 초안은 표시한다', async () => {
    previewMock.mockResolvedValue(fail(500, 'UNKNOWN'));
    latestMock.mockResolvedValue(ok(DRAFT));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('초안')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '승인하기' })).toBeEnabled();
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

  it('draft — confirmedAt null을 허용하고 1탭 승인 응답·재계산 안내를 그대로 그린다', async () => {
    latestMock.mockResolvedValue(ok(DRAFT));
    approveMock.mockResolvedValue(
      ok({
        ...ORDER,
        items: [{ ...ORDER.items[0]!, quantity: '9' }],
      }),
    );
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('초안')).toBeInTheDocument());
    expect(screen.getByText(/자동으로 확정돼요/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '품목 편집 (준비 중)' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '승인하기' }));
    await waitFor(() => expect(screen.getByText('재료가 조금 바뀌었어요')).toBeInTheDocument());
    expect(screen.getByText('확정')).toBeInTheDocument();
    expect(approveMock).toHaveBeenCalledWith('ord-1');
  });

  it('approve 409는 이미 확정 안내 후 latest를 재조회한다', async () => {
    latestMock.mockResolvedValueOnce(ok(DRAFT)).mockResolvedValueOnce(ok(ORDER));
    approveMock.mockResolvedValue(fail(409, 'ORDER_ALREADY_CONFIRMED'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByRole('button', { name: '승인하기' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '승인하기' }));
    await waitFor(() => expect(screen.getByText('이미 확정됐어요')).toBeInTheDocument());
    expect(screen.getByText('확정')).toBeInTheDocument();
  });

  it('awaiting_user 차단 사유는 설정 또는 다시 계산 액션으로 연결한다', async () => {
    latestMock.mockResolvedValue(
      ok({ ...DRAFT, status: 'awaiting_user', blockedReason: 'STORE_DISCONNECTED' }),
    );
    const first = renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('스토어 연동이 풀렸어요')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '설정으로' }));
    expect(routerMock.push).toHaveBeenCalledWith('/settings');
    first.unmount();

    latestMock.mockResolvedValue(
      ok({ ...DRAFT, status: 'awaiting_user', blockedReason: 'UNMATCHED_RATIO' }),
    );
    recalculateMock.mockResolvedValue(
      ok({
        ...DRAFT,
        status: 'awaiting_user',
        blockedReason: 'UNMATCHED_RATIO',
        items: [
          { ...DRAFT.items[0]!, name: '시세없음', matched: false, title: null, unitPrice: null },
          { ...DRAFT.items[0]!, name: '가격없음', title: '가격 없는 후보', unitPrice: null },
        ],
      }),
    );
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('못 찾은 재료가 많아요')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '장바구니 확인' }));
    await waitFor(() => expect(recalculateMock).toHaveBeenCalledWith('ord-1'));
    expect(screen.getByText('시세없음')).toBeInTheDocument();
    expect(screen.getByText('가격 없는 후보')).toBeInTheDocument();
  });

  it('awaiting_user 재계산 실패는 서버 에러 코드를 표시한다', async () => {
    latestMock.mockResolvedValue(
      ok({ ...DRAFT, status: 'awaiting_user', blockedReason: 'UNMATCHED_RATIO' }),
    );
    recalculateMock.mockResolvedValue(fail(429, 'RATE_LIMITED'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByRole('button', { name: '장바구니 확인' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '장바구니 확인' }));
    await waitFor(() => {
      expect(screen.getByText(/요청이 많아 잠시 쉬어가는 중/)).toBeInTheDocument();
    });
  });

  it('draft 건너뛰기는 cycle skip 후 cancelled latest를 다시 그린다', async () => {
    latestMock
      .mockResolvedValueOnce(ok(DRAFT))
      .mockResolvedValueOnce(ok({ ...DRAFT, status: 'cancelled', autoConfirmAt: null }));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByRole('button', { name: '이번 주 건너뛰기' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '이번 주 건너뛰기' }));
    await waitFor(() => expect(screen.getByText('이번 주문은 취소됐어요')).toBeInTheDocument());
    expect(skipMock).toHaveBeenCalledTimes(1);
  });

  it('confirmed 취소 성공과 취소 기간 오류를 처리한다', async () => {
    latestMock.mockResolvedValue(ok(ORDER));
    const first = renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByRole('button', { name: '주문 취소' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '주문 취소' }));
    await waitFor(() => expect(screen.getByText('이번 주문은 취소됐어요')).toBeInTheDocument());
    first.unmount();

    cancelMock.mockResolvedValue(fail(409, 'ORDER_CANCEL_WINDOW_CLOSED'));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByRole('button', { name: '주문 취소' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '주문 취소' }));
    await waitFor(() => expect(screen.getByText('주문 취소 가능 기간이 지났어요.')).toBeInTheDocument());
  });

  it('expired/cancelled는 조작 없이 다음 사이클 안내만 표시한다', async () => {
    latestMock.mockResolvedValue(ok({ ...ORDER, status: 'expired', confirmedAt: null }));
    const first = renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('승인 시간이 지났어요')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '승인하기' })).not.toBeInTheDocument();
    first.unmount();

    latestMock.mockResolvedValue(ok({ ...ORDER, status: 'cancelled' }));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('이번 주문은 취소됐어요')).toBeInTheDocument());
  });

  it('failed는 되살리는 액션 없이 다음 사이클 안내만 표시한다', async () => {
    latestMock.mockResolvedValue(ok({ ...DRAFT, status: 'failed' }));
    renderWithIntl(<OrdersController />);
    await waitFor(() => expect(screen.getByText('장바구니를 준비하지 못했어요')).toBeInTheDocument());
    expect(screen.getByText(/다음 주문 제안/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(recalculateMock).not.toHaveBeenCalled();
  });
});
