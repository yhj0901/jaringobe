import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, within } from '@testing-library/react';
import { MemberHomeController } from '@/features/mealplan/MemberHomeController';
import { mapPlanToViewModel } from '@/features/mealplan/mapPlanToViewModel';
import type { MealPlanResponse } from '@/features/mealplan/types';
import type { MemberHomeState } from '@/features/mealplan/useMemberHome';
import type { CycleHookState } from '@/features/cycle/useCycle';
import type { CycleState } from '@/features/cycle/types';
import { approveOrder, cancelOrder, fetchLatestOrder } from '@/features/order/api';
import { renderWithIntl } from '@/test/renderWithIntl';

const state: { current: MemberHomeState } = { current: undefined as unknown as MemberHomeState };
const routerMock = { push: vi.fn(), replace: vi.fn() };

vi.mock('@/features/mealplan/useMemberHome', () => ({
  useMemberHome: () => state.current,
}));
vi.mock('@/features/guest/GuestHomeController', () => ({
  GuestHomeController: () => <div data-testid="guest-home" />,
}));
const autoOrderState: {
  current: {
    active: boolean;
    stores: { id: string; name: string }[];
    recommendedItems: string[];
    moreCount: number;
    latestOrder: null;
    loading: boolean;
  };
} = {
  current: {
    active: false,
    stores: [],
    recommendedItems: [],
    moreCount: 0,
    latestOrder: null,
    loading: false,
  },
};
vi.mock('@/features/order/useMemberAutoOrder', () => ({
  useMemberAutoOrder: () => autoOrderState.current,
}));
const cycleState: { current: CycleHookState } = {
  current: {
    status: 'error',
    cycle: null,
    saving: false,
    errorCode: null,
    reload: vi.fn(),
    updateSettings: vi.fn(),
    skip: vi.fn(),
  },
};
vi.mock('@/features/cycle/useCycle', () => ({
  useCycle: () => cycleState.current,
}));
vi.mock('@/features/order/api', () => ({
  approveOrder: vi.fn(),
  cancelOrder: vi.fn(),
  fetchLatestOrder: vi.fn(),
}));
vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/',
  };
});

const PLAN: MealPlanResponse = {
  id: 'plan-1',
  status: 'ready',
  region: 'KR',
  currency: 'KRW',
  periodStart: '2026-07-08',
  periodEnd: '2026-07-09',
  budgetSummary: {
    budget: { amount: '700000.00', currency: 'KRW' },
    plannedCost: { amount: '612300.00', currency: 'KRW' },
    remaining: { amount: '87700.00', currency: 'KRW' },
    withinBudget: true,
  },
  meals: [
    {
      id: 'm1',
      planDate: '2026-07-08',
      mealType: 'breakfast',
      recipeName: '토스트',
      ingredients: [
        {
          id: 'i1',
          name: '식빵',
          quantity: '2',
          unit: 'ea',
          estCost: { amount: '1200.00', currency: 'KRW' },
        },
      ],
    },
    {
      id: 'm2',
      planDate: '2026-07-09',
      mealType: 'lunch',
      recipeName: '비빔국수',
      ingredients: [],
    },
  ],
  notes: [],
};

const CYCLE: CycleState = {
  enabled: true,
  frequency: 'weekly',
  anchorWeekday: 0,
  timezone: 'Asia/Seoul',
  autoConfirm: true,
  cycleStart: '2026-09-06',
  cycleDays: 7,
  stage: 'drafted',
  nextRunAt: '2026-09-13T00:00:00Z',
  skippedCycleStart: null,
  weeklyLimit: null,
  mealPlan: { id: 'plan-1', status: 'ready' },
  draftOrder: {
    id: 'order-1',
    status: 'draft',
    estimatedTotal: { amount: '22000', currency: 'KRW' },
    autoConfirmAt: '2026-09-06T12:00:00Z',
    blockedReason: null,
    deliveryEta: null,
  },
  simulation: true,
};

function baseState(overrides: Partial<MemberHomeState> = {}): MemberHomeState {
  return {
    status: 'loading',
    onboardingCompleted: true,
    country: 'KR',
    plan: null,
    viewModel: null,
    budget: null,
    householdSize: 4,
    generation: 'idle',
    generationError: null,
    backgroundNotice: false,
    planFailed: false,
    createRequired: false,
    ackCreateRequired: vi.fn(),
    pendingMealIds: new Set<string>(),
    selectDate: vi.fn(),
    createPlan: vi.fn().mockResolvedValue(undefined),
    regeneratePlan: vi.fn().mockResolvedValue(undefined),
    toggleMealCompletion: vi.fn().mockResolvedValue(undefined),
    retryGenerate: vi.fn().mockResolvedValue(undefined),
    dismissGenerationError: vi.fn(),
    dismissBackgroundNotice: vi.fn(),
    completeBudgetPlan: vi.fn().mockResolvedValue('created'),
    reload: vi.fn(),
    ...overrides,
  };
}

function readyState(plan: MealPlanResponse = PLAN, overrides: Partial<MemberHomeState> = {}) {
  return baseState({
    status: 'ready',
    plan,
    viewModel: mapPlanToViewModel(plan, { selectedDate: '2026-07-08' }),
    ...overrides,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  state.current = baseState();
  autoOrderState.current = {
    active: false,
    stores: [],
    recommendedItems: [],
    moreCount: 0,
    latestOrder: null,
    loading: false,
  };
  cycleState.current = {
    status: 'error',
    cycle: null,
    saving: false,
    errorCode: null,
    reload: vi.fn(),
    updateSettings: vi.fn().mockResolvedValue(true),
    skip: vi.fn().mockResolvedValue(true),
  };
});

describe('MemberHomeController 상태 분기 (ui-design 7장)', () => {
  it('loading → aria-busy 스켈레톤', () => {
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('guest(401 폴백) → GuestHomeController 렌더 (게스트 동작 불변)', () => {
    state.current = baseState({ status: 'guest' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByTestId('guest-home')).toBeInTheDocument();
  });

  it('error → 에러 안내 + 다시 불러오기', () => {
    state.current = baseState({ status: 'error' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByRole('alert')).toHaveTextContent('식단을 불러오지 못했어요');
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(state.current.reload).toHaveBeenCalledTimes(1);
  });

  it('budget-required → 샘플 홈 + 온보딩 유도 배너 (FR-316, BudgetPlanGate 전면 제거)', () => {
    state.current = baseState({ status: 'budget-required' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.queryByText('먼저 예산안을 만들어 주세요')).not.toBeInTheDocument();
    // 샘플 홈 셸 + 상단 배너
    expect(screen.getByText('남은 예산')).toBeInTheDocument();
    expect(screen.getAllByText('예시').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: '설정 마치고 식단 만들기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/onboarding');
  });
});

describe('MemberHomeController 빈 상태 — 샘플 홈 + 배너 (FR-316/202/203/204)', () => {
  it('온보딩 미완료 → "설정 마치고 식단 만들기" 배너 → /onboarding', () => {
    state.current = baseState({ status: 'empty', onboardingCompleted: false });
    renderWithIntl(<MemberHomeController />);

    // 체험 배지 없음 + "예시" 라벨 유지 (ui-design 8장)
    expect(screen.queryByText('체험 모드')).not.toBeInTheDocument();
    expect(screen.getAllByText('예시').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: '설정 마치고 식단 만들기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/onboarding');
  });

  it('온보딩 완료 → "내 식단 만들기" 배너 → 생성 시트 → 제출 시 createPlan 호출', () => {
    state.current = baseState({ status: 'empty' });
    renderWithIntl(<MemberHomeController />);

    expect(screen.queryByText('체험 모드')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '내 식단 만들기' }));
    fireEvent.click(screen.getByRole('button', { name: '식단 생성하기' }));
    expect(state.current.createPlan).toHaveBeenCalledWith({
      days: 7,
      allergies: [],
      preferences: [],
    });
    // 제출 후 시트 닫힘
    expect(screen.queryByRole('button', { name: '식단 생성하기' })).not.toBeInTheDocument();
    expect(routerMock.push).not.toHaveBeenCalled();
  });

  it('생성 중 → GenerationLoading 오버레이 + 배너 CTA 비활성', () => {
    state.current = baseState({ status: 'empty', generation: 'creating' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '내 식단 만들기' })).toBeDisabled();
  });

  it('빈 상태 탭바: fridge → /fridge, cart → /orders (FR-208/v1.7)', () => {
    state.current = baseState({ status: 'empty', onboardingCompleted: false });
    renderWithIntl(<MemberHomeController />);
    fireEvent.click(screen.getByRole('button', { name: '냉장고' }));
    expect(routerMock.push).toHaveBeenCalledWith('/fridge');
    fireEvent.click(screen.getByRole('button', { name: '장바구니' }));
    expect(routerMock.push).toHaveBeenCalledWith('/orders');
  });

  it('실패 → 재시도 배너 (retryGenerate)', () => {
    state.current = baseState({ status: 'empty', generationError: 'failed' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByRole('alert')).toHaveTextContent('식단 생성에 실패했어요');
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(state.current.retryGenerate).toHaveBeenCalledTimes(1);
  });

  it('429 → 대기 안내 (재시도 버튼 없음) + 닫기', () => {
    state.current = baseState({ status: 'empty', generationError: 'rate-limited' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText(/1분 후 다시 시도해 주세요/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '다시 시도' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(state.current.dismissGenerationError).toHaveBeenCalledTimes(1);
  });

  it('폴링 3분 초과 → "완료되면 알려드릴게요" 안내 배너 + 닫기 (ui-design 12장)', () => {
    state.current = baseState({ status: 'empty', backgroundNotice: true });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText(/완료되면 알려드릴게요/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(state.current.dismissBackgroundNotice).toHaveBeenCalledTimes(1);
  });

  it('createRequired → 생성 시트 오픈 + 안내 토스트 + 신호 소비 (api-spec 3-5 v1.5.1)', () => {
    state.current = baseState({ status: 'empty', createRequired: true });
    renderWithIntl(<MemberHomeController />);

    expect(state.current.ackCreateRequired).toHaveBeenCalledTimes(1);
    // 기존 PlanCreateSheet 재사용 — 시트 제목으로 오픈 확인
    expect(screen.getByRole('heading', { name: '내 식단 만들기' })).toBeInTheDocument();
    expect(
      screen.getByText('이전 요청 정보를 찾을 수 없어요. 새 식단으로 만들어 주세요.'),
    ).toBeInTheDocument();
  });

  it('latest.status=failed → 재시도 배너 → 재생성 호출 (ui-design 12장)', () => {
    state.current = baseState({ status: 'empty', planFailed: true });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByRole('alert')).toHaveTextContent('지난 식단 생성에 실패했어요');
    fireEvent.click(screen.getByRole('button', { name: '다시 생성하기' }));
    expect(state.current.regeneratePlan).toHaveBeenCalledTimes(1);
  });
});

describe('MemberHomeController 식단 홈 (FR-205/206/208/209)', () => {
  it('회원 셸: 끼니 행(재료·추정 비용) + 잠금 카드 + 체험 배지 없음', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    expect(screen.queryByText('체험 모드')).not.toBeInTheDocument();
    expect(screen.getByText('토스트')).toBeInTheDocument();
    expect(screen.getByText('식빵')).toBeInTheDocument();
    expect(screen.getByText('₩1,200')).toBeInTheDocument();
    // 냉장고는 활성(→/fridge), 자동주문은 AutoOrderCard (잠금 해제, v1.7)
    expect(screen.getByText('사용하기')).toBeInTheDocument();
    expect(screen.queryByText('준비 중')).not.toBeInTheDocument();
    expect(screen.getByText('대기 중')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '스토어 연동하기' })).toBeInTheDocument();
    expect(screen.queryByText('이번 주 주문 추천')).not.toBeInTheDocument();
  });

  it('마이 탭 → /settings 이동 (ui-design 9장, FR-401)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);
    fireEvent.click(screen.getByRole('button', { name: '마이' }));
    expect(routerMock.push).toHaveBeenCalledWith('/settings');
  });

  it('빈 상태(샘플 홈)에서도 마이 탭 → /settings 이동', () => {
    state.current = baseState({ status: 'empty' });
    renderWithIntl(<MemberHomeController />);
    fireEvent.click(screen.getByRole('button', { name: '마이' }));
    expect(routerMock.push).toHaveBeenCalledWith('/settings');
  });

  it('주간 스트립 일자 버튼 → selectDate (FR-205)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    const active = screen.getByRole('button', { name: '수 8' });
    expect(active).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '목 9' }));
    expect(state.current.selectDate).toHaveBeenCalledWith('2026-07-09');
  });

  it('재생성 버튼 → 확인 다이얼로그 → 확인 시 regeneratePlan (FR-209)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '다시 만들기' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('식단을 전체 다시 만들까요?')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '취소' }));
    expect(state.current.regeneratePlan).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '다시 만들기' }));
    fireEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: '다시 만들기' }),
    );
    expect(state.current.regeneratePlan).toHaveBeenCalledTimes(1);
  });

  it('예산 초과 → OverBudgetBanner → 재생성 유도 (FR-206)', () => {
    const overPlan: MealPlanResponse = {
      ...PLAN,
      status: 'over_budget',
      budgetSummary: {
        budget: { amount: '700000.00', currency: 'KRW' },
        plannedCost: { amount: '712300.00', currency: 'KRW' },
        remaining: { amount: '-12300.00', currency: 'KRW' },
        withinBudget: false,
      },
    };
    state.current = readyState(overPlan);
    renderWithIntl(<MemberHomeController />);

    expect(screen.getByRole('alert')).toHaveTextContent('식단이 예산을 초과했어요');
    fireEvent.click(screen.getByRole('button', { name: '예산에 맞게 다시 생성' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('탭바: fridge → /fridge 이동, cart → /orders 이동 (v1.7)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '냉장고' }));
    expect(routerMock.push).toHaveBeenCalledWith('/fridge');

    fireEvent.click(screen.getByRole('button', { name: '장바구니' }));
    expect(routerMock.push).toHaveBeenCalledWith('/orders');
    expect(screen.queryByText('아직 준비 중인 기능이에요. 곧 만나요!')).not.toBeInTheDocument();
  });

  it('자동주문 비활성 CTA → /settings, 활성 CTA → /orders', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);
    fireEvent.click(screen.getByRole('button', { name: '스토어 연동하기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/settings');
  });

  it('스토어 연동 + 추천 칩 → "장바구니 보기" CTA가 /orders 로 이동', () => {
    autoOrderState.current = {
      active: true,
      stores: [{ id: 'kurly', name: '마켓컬리' }],
      recommendedItems: ['계란', '양파'],
      moreCount: 0,
      latestOrder: null,
      loading: false,
    };
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('마켓컬리')).toBeInTheDocument();
    expect(screen.getByText('계란')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '장바구니 보기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/orders');
  });

  it('탭바: 식단 → "프리미엄 구독" 안내 (구독 편입 예정)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '식단' }));
    expect(screen.getByText('프리미엄 구독 서비스로 준비 중이에요. 곧 만나요!')).toBeInTheDocument();
  });

  it('country=US → 홈 헤더 "글로벌" 배지 노출 (FR-605)', () => {
    state.current = readyState(PLAN, { country: 'US' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('글로벌')).toBeInTheDocument();
  });

  it('country=KR → 글로벌 배지 미노출', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);
    expect(screen.queryByText('글로벌')).not.toBeInTheDocument();
  });

  it('끼니 행 클릭 → 레시피 시트(메타 3칩·재료 칩·기본 조리법) 오픈 후 닫기 (FR-504)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '토스트 레시피 보기' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('AI 추천 레시피')).toBeInTheDocument();
    // 메타 3칩: 기본 시간/난이도 + householdSize(4) 기반 인분
    expect(within(dialog).getByText('약 20분')).toBeInTheDocument();
    expect(within(dialog).getByText('쉬움')).toBeInTheDocument();
    expect(within(dialog).getByText('4인분')).toBeInTheDocument();
    // 재료 칩 (name+quantity+unit)
    expect(within(dialog).getByText('식빵 2ea')).toBeInTheDocument();
    // steps 부재 → 기본 조리법 3단계
    expect(within(dialog).getByText(/재료를 깨끗이 씻고/)).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '닫기' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('완료 버튼 클릭 → toggleMealCompletion(mealId) 호출 (FR-501/503)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);
    fireEvent.click(screen.getByRole('button', { name: '토스트 식사 완료 체크' }));
    expect(state.current.toggleMealCompletion).toHaveBeenCalledWith('m1');
  });

  it('재생성 진행 중 → GenerationLoading 오버레이', () => {
    state.current = readyState(PLAN, { generation: 'regenerating' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
  });

  it('사이클 초안을 홈에서 1탭 승인하고 최신 상태를 다시 불러온다', async () => {
    cycleState.current = { ...cycleState.current, status: 'ready', cycle: CYCLE };
    vi.mocked(approveOrder).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        id: 'order-1',
        store: 'coupang',
        status: 'confirmed',
        frequency: 'weekly',
        nextSuggestedAt: '2026-09-13T00:00:00Z',
        estimatedTotal: { amount: '22000', currency: 'KRW' },
        confirmedAt: '2026-09-06T03:00:00Z',
        simulation: true,
        items: [],
        cycleStart: '2026-09-06',
        deliveryEta: null,
        inboundAt: null,
        deliveryState: 'pending',
        deliveryConfirmAttempts: 0,
        autoConfirmed: false,
        autoConfirmAt: null,
        blockedReason: null,
      },
    });
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '승인하기' }));
    expect(await screen.findByText('장바구니를 승인했어요.')).toBeInTheDocument();
    expect(approveOrder).toHaveBeenCalledWith('order-1');
    expect(cycleState.current.reload).toHaveBeenCalledTimes(1);
  });

  it('사이클 건너뛰기 실패를 공통 오류로 안내한다', async () => {
    cycleState.current = {
      ...cycleState.current,
      status: 'ready',
      cycle: CYCLE,
      skip: vi.fn().mockResolvedValue(false),
    };
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '이번 주 건너뛰기' }));
    expect(await screen.findByText(/일시적인 오류가 발생했어요/)).toBeInTheDocument();
  });

  it('확정 사이클 주문을 홈에서 취소하고 상태를 갱신한다', async () => {
    cycleState.current = {
      ...cycleState.current,
      status: 'ready',
      cycle: { ...CYCLE, stage: 'confirmed' },
    };
    vi.mocked(fetchLatestOrder).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        id: 'order-1',
        store: 'coupang',
        status: 'confirmed',
        frequency: 'weekly',
        nextSuggestedAt: '2026-09-13T00:00:00Z',
        estimatedTotal: { amount: '22000', currency: 'KRW' },
        confirmedAt: '2026-09-06T03:00:00Z',
        simulation: true,
        items: [],
        cycleStart: '2026-09-06',
        deliveryEta: null,
        inboundAt: null,
        deliveryState: 'pending',
        deliveryConfirmAttempts: 0,
        autoConfirmed: false,
        autoConfirmAt: null,
        blockedReason: null,
      },
    });
    vi.mocked(cancelOrder).mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        id: 'order-1',
        store: 'coupang',
        status: 'cancelled',
        frequency: 'weekly',
        nextSuggestedAt: '2026-09-13T00:00:00Z',
        estimatedTotal: { amount: '22000', currency: 'KRW' },
        confirmedAt: '2026-09-06T03:00:00Z',
        simulation: true,
        items: [],
        cycleStart: '2026-09-06',
        deliveryEta: null,
        inboundAt: null,
        deliveryState: 'pending',
        deliveryConfirmAttempts: 0,
        autoConfirmed: false,
        autoConfirmAt: null,
        blockedReason: null,
      },
    });
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '주문 취소' }));
    expect(await screen.findByText('주문을 취소했어요.')).toBeInTheDocument();
    expect(cancelOrder).toHaveBeenCalledWith('order-1');
    expect(cycleState.current.reload).toHaveBeenCalledTimes(1);
  });
});
