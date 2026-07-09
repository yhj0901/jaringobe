import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, within } from '@testing-library/react';
import { MemberHomeController } from '@/features/mealplan/MemberHomeController';
import { mapPlanToViewModel } from '@/features/mealplan/mapPlanToViewModel';
import type { MealPlanResponse } from '@/features/mealplan/types';
import type { MemberHomeState } from '@/features/mealplan/useMemberHome';
import { renderWithIntl } from '@/test/renderWithIntl';

const state: { current: MemberHomeState } = { current: undefined as unknown as MemberHomeState };

vi.mock('@/features/mealplan/useMemberHome', () => ({
  useMemberHome: () => state.current,
}));
vi.mock('@/features/guest/GuestHomeController', () => ({
  GuestHomeController: () => <div data-testid="guest-home" />,
}));

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

function baseState(overrides: Partial<MemberHomeState> = {}): MemberHomeState {
  return {
    status: 'loading',
    plan: null,
    viewModel: null,
    budget: null,
    generation: 'idle',
    generationError: null,
    selectDate: vi.fn(),
    createPlan: vi.fn().mockResolvedValue(undefined),
    regeneratePlan: vi.fn().mockResolvedValue(undefined),
    retryGenerate: vi.fn().mockResolvedValue(undefined),
    dismissGenerationError: vi.fn(),
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
  state.current = baseState();
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

  it('budget-required → BudgetPlanGate (FR-207)', () => {
    state.current = baseState({ status: 'budget-required' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('먼저 예산안을 만들어 주세요')).toBeInTheDocument();
  });
});

describe('MemberHomeController 빈 상태 (FR-202/203/204)', () => {
  it('EmptyPlanHero + 잠금 카드, CTA → 생성 시트 → 제출 시 createPlan 호출', () => {
    state.current = baseState({
      status: 'empty',
      budget: { amount: '500000.00', currency: 'KRW' },
    });
    renderWithIntl(<MemberHomeController />);

    expect(screen.getByText('₩500,000')).toBeInTheDocument();
    expect(screen.getAllByText('준비 중')).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: '내 식단 만들기' }));
    fireEvent.click(screen.getByRole('button', { name: '식단 생성하기' }));
    expect(state.current.createPlan).toHaveBeenCalledWith({
      days: 7,
      allergies: [],
      preferences: [],
    });
    // 제출 후 시트 닫힘
    expect(screen.queryByRole('button', { name: '식단 생성하기' })).not.toBeInTheDocument();
  });

  it('생성 중 → GenerationLoading 오버레이 + CTA 비활성', () => {
    state.current = baseState({ status: 'empty', generation: 'creating' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '내 식단 만들기' })).toBeDisabled();
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
});

describe('MemberHomeController 식단 홈 (FR-205/206/208/209)', () => {
  it('회원 셸: 끼니 행(재료·추정 비용) + 잠금 카드 + 체험 배지 없음', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    expect(screen.queryByText('체험 모드')).not.toBeInTheDocument();
    expect(screen.getByText('토스트')).toBeInTheDocument();
    expect(screen.getByText('식빵')).toBeInTheDocument();
    expect(screen.getByText('₩1,200')).toBeInTheDocument();
    // 냉장고/자동주문 잠금 카드 (게스트 샘플 노출 금지)
    expect(screen.getAllByText('준비 중')).toHaveLength(2);
    expect(screen.queryByText('이번 주 주문 추천')).not.toBeInTheDocument();
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
      budgetSummary: { ...PLAN.budgetSummary, withinBudget: false },
    };
    state.current = readyState(overPlan);
    renderWithIntl(<MemberHomeController />);

    expect(screen.getByRole('alert')).toHaveTextContent('식단이 예산을 초과했어요');
    fireEvent.click(screen.getByRole('button', { name: '예산에 맞게 다시 생성' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('탭바: fridge/cart → "준비 중" 안내, meal → 식단 섹션 스크롤 (FR-208, 가입 게이트 아님)', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);

    fireEvent.click(screen.getByRole('button', { name: '냉장고' }));
    expect(screen.getByText('아직 준비 중인 기능이에요. 곧 만나요!')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '식단' }));
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it('조리법 보기 → "준비 중" 안내 (조리법 상세는 범위 외)', () => {
    state.current = readyState();
    renderWithIntl(<MemberHomeController />);
    fireEvent.click(
      screen.getAllByRole('button', { name: '전체 조리법 보기' })[0] as HTMLElement,
    );
    expect(screen.getByText('아직 준비 중인 기능이에요. 곧 만나요!')).toBeInTheDocument();
  });

  it('재생성 진행 중 → GenerationLoading 오버레이', () => {
    state.current = readyState(PLAN, { generation: 'regenerating' });
    renderWithIntl(<MemberHomeController />);
    expect(screen.getByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
  });
});
