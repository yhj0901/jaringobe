import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useMemberHome } from '@/features/mealplan/useMemberHome';
import { fetchMe } from '@/features/auth/useSession';
import {
  createMealPlan,
  fetchLatestMealPlan,
  regenerateMealPlan,
  setMealCompletion,
} from '@/features/mealplan/api';
import { fetchHousehold } from '@/features/household/api';
import { createOnboardingPlan } from '@/features/budget/createOnboardingPlan';
import type { MealPlanMeal, MealPlanResponse } from '@/features/mealplan/types';
import type { ApiResult } from '@/shared/api/client';

vi.mock('@/features/auth/useSession', () => ({ fetchMe: vi.fn() }));
vi.mock('@/features/mealplan/api', () => ({
  fetchLatestMealPlan: vi.fn(),
  createMealPlan: vi.fn(),
  regenerateMealPlan: vi.fn(),
  setMealCompletion: vi.fn(),
}));
vi.mock('@/features/household/api', () => ({ fetchHousehold: vi.fn() }));
vi.mock('@/features/budget/createOnboardingPlan', () => ({ createOnboardingPlan: vi.fn() }));

const fetchMeMock = vi.mocked(fetchMe);
const latestMock = vi.mocked(fetchLatestMealPlan);
const createMock = vi.mocked(createMealPlan);
const regenerateMock = vi.mocked(regenerateMealPlan);
const completionMock = vi.mocked(setMealCompletion);
const householdMock = vi.mocked(fetchHousehold);
const onboardingMock = vi.mocked(createOnboardingPlan);

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function err(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

const ME = {
  id: 'u1',
  nickname: '자린이',
  email: null,
  profileImageUrl: null,
  locale: 'ko',
  country: 'KR',
  currency: 'KRW',
  onboardingCompleted: true,
  hasBudgetPlan: true,
};

const PLAN: MealPlanResponse = {
  id: 'plan-1',
  status: 'ready',
  region: 'KR',
  currency: 'KRW',
  periodStart: '2026-07-08',
  periodEnd: '2026-07-14',
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
      recipeName: '계란볶음밥',
      ingredients: [],
    },
  ],
  notes: [],
};

const GUEST_PLAN = {
  householdSize: 2,
  amount: '500000',
  currency: 'KRW' as const,
  mealDirection: 'health' as const,
};

beforeEach(() => {
  vi.clearAllMocks();
  householdMock.mockResolvedValue(ok({ members: [], size: 4 }));
});

describe('useMemberHome 분기 (ui-design 7장)', () => {
  it('users/me 401 → guest (게스트 홈 폴백)', async () => {
    fetchMeMock.mockResolvedValue(err(401, 'AUTH_REQUIRED'));
    const { result } = renderHook(() => useMemberHome());
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('guest'));
    expect(latestMock).not.toHaveBeenCalled();
  });

  it('users/me 5xx → error', async () => {
    fetchMeMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useMemberHome());
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('hasBudgetPlan=false → budget-required (FR-207) — latest 는 호출하지 않는다', async () => {
    fetchMeMock.mockResolvedValue(ok({ ...ME, hasBudgetPlan: false }));
    const { result } = renderHook(() => useMemberHome());
    await waitFor(() => expect(result.current.status).toBe('budget-required'));
    expect(latestMock).not.toHaveBeenCalled();
  });

  it('latest 404 MEALPLAN_NOT_FOUND → empty (FR-202)', async () => {
    fetchMeMock.mockResolvedValue(ok(ME));
    latestMock.mockResolvedValue(err(404, 'MEALPLAN_NOT_FOUND'));
    const { result } = renderHook(() => useMemberHome());
    await waitFor(() => expect(result.current.status).toBe('empty'));
    expect(result.current.viewModel).toBeNull();
  });

  it('latest 200 → ready + member ViewModel (FR-201/205)', async () => {
    fetchMeMock.mockResolvedValue(ok(ME));
    latestMock.mockResolvedValue(ok(PLAN));
    const { result } = renderHook(() => useMemberHome());
    await waitFor(() => expect(result.current.status).toBe('ready'));

    expect(result.current.plan?.id).toBe('plan-1');
    expect(result.current.viewModel?.mode).toBe('member');
    expect(result.current.viewModel?.planId).toBe('plan-1');

    // 주간 스트립 일자 이동 (FR-205)
    act(() => result.current.selectDate('2026-07-10'));
    await waitFor(() => expect(result.current.viewModel?.selectedDate).toBe('2026-07-10'));
  });

  it('latest 5xx → error, reload 로 재조회한다', async () => {
    fetchMeMock.mockResolvedValue(ok(ME));
    latestMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useMemberHome());
    await waitFor(() => expect(result.current.status).toBe('error'));

    latestMock.mockResolvedValueOnce(ok(PLAN));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.status).toBe('ready'));
  });
});

describe('useMemberHome 생성/재생성 (FR-203/204/209)', () => {
  async function setupEmpty() {
    fetchMeMock.mockResolvedValue(ok(ME));
    latestMock.mockResolvedValue(err(404, 'MEALPLAN_NOT_FOUND'));
    const rendered = renderHook(() => useMemberHome());
    await waitFor(() => expect(rendered.result.current.status).toBe('empty'));
    return rendered;
  }

  it('createPlan 성공 → ready, mealsPerDay=3 고정으로 요청한다', async () => {
    const { result } = await setupEmpty();
    createMock.mockResolvedValue(ok(PLAN, 201));

    await act(() =>
      result.current.createPlan({ days: 7, allergies: ['땅콩'], preferences: ['한식'] }),
    );

    expect(createMock).toHaveBeenCalledWith({
      days: 7,
      mealsPerDay: 3,
      allergies: ['땅콩'],
      preferences: ['한식'],
    });
    expect(result.current.status).toBe('ready');
    expect(result.current.generation).toBe('idle');
    expect(result.current.generationError).toBeNull();
  });

  it('생성 진행 중 재호출은 무시된다 (연타 방지)', async () => {
    const { result } = await setupEmpty();
    let resolveCreate: (value: ApiResult<MealPlanResponse>) => void = () => undefined;
    createMock.mockImplementation(
      () => new Promise<ApiResult<MealPlanResponse>>((resolve) => (resolveCreate = resolve)),
    );

    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.createPlan({ days: 7, allergies: [], preferences: [] });
    });
    await waitFor(() => expect(result.current.generation).toBe('creating'));
    await act(() => result.current.createPlan({ days: 3, allergies: [], preferences: [] }));
    expect(createMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveCreate(ok(PLAN, 201));
      await first;
    });
    expect(result.current.status).toBe('ready');
  });

  it('429 → rate-limited 대기 안내, 그 외 실패 → failed + retryGenerate 로 동일 입력 재시도', async () => {
    const { result } = await setupEmpty();

    createMock.mockResolvedValueOnce(err(429, 'RATE_LIMITED'));
    await act(() => result.current.createPlan({ days: 7, allergies: [], preferences: [] }));
    expect(result.current.generationError).toBe('rate-limited');
    expect(result.current.status).toBe('empty');

    createMock.mockResolvedValueOnce(err(0, 'NETWORK_ERROR'));
    await act(() => result.current.createPlan({ days: 7, allergies: ['우유'], preferences: [] }));
    expect(result.current.generationError).toBe('failed');

    act(() => result.current.dismissGenerationError());
    expect(result.current.generationError).toBeNull();

    createMock.mockResolvedValueOnce(ok(PLAN, 201));
    await act(() => result.current.retryGenerate());
    expect(createMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ days: 7, allergies: ['우유'] }),
    );
    expect(result.current.status).toBe('ready');
  });

  it('regeneratePlan → POST regenerate 후 plan 교체, 실패 시 retryGenerate 는 재생성을 재시도 (FR-209)', async () => {
    fetchMeMock.mockResolvedValue(ok(ME));
    latestMock.mockResolvedValue(ok(PLAN));
    const { result } = renderHook(() => useMemberHome());
    await waitFor(() => expect(result.current.status).toBe('ready'));

    regenerateMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    await act(() => result.current.regeneratePlan());
    expect(regenerateMock).toHaveBeenCalledWith('plan-1');
    expect(result.current.generationError).toBe('failed');
    expect(result.current.plan?.id).toBe('plan-1');

    regenerateMock.mockResolvedValueOnce(ok({ ...PLAN, id: 'plan-2' }));
    await act(() => result.current.retryGenerate());
    expect(regenerateMock).toHaveBeenCalledTimes(2);
    expect(result.current.plan?.id).toBe('plan-2');
    expect(result.current.generationError).toBeNull();
  });

  it('plan 이 없으면 regeneratePlan 은 아무것도 하지 않는다', async () => {
    const { result } = await setupEmpty();
    await act(() => result.current.regeneratePlan());
    expect(regenerateMock).not.toHaveBeenCalled();
  });
});

describe('useMemberHome 온보딩 예산안 (FR-207)', () => {
  async function setupBudgetRequired() {
    fetchMeMock.mockResolvedValue(ok({ ...ME, hasBudgetPlan: false }));
    const rendered = renderHook(() => useMemberHome());
    await waitFor(() => expect(rendered.result.current.status).toBe('budget-required'));
    return rendered;
  }

  it('created → empty + 확정 예산 노출 (빈 상태 히어로 금액)', async () => {
    const { result } = await setupBudgetRequired();
    onboardingMock.mockResolvedValue({
      kind: 'created',
      plan: {
        id: 'b1',
        householdSize: 2,
        budget: { amount: '500000.00', currency: 'KRW' },
        mealDirection: 'health',
        source: 'onboarding',
        createdAt: '2026-07-09T04:00:00Z',
      },
    });

    let kind = '';
    await act(async () => {
      kind = await result.current.completeBudgetPlan(GUEST_PLAN);
    });
    expect(kind).toBe('created');
    expect(result.current.status).toBe('empty');
    expect(result.current.budget).toEqual({ amount: '500000.00', currency: 'KRW' });
  });

  it('already-exists → 최신 식단 재조회로 이어진다', async () => {
    const { result } = await setupBudgetRequired();
    onboardingMock.mockResolvedValue({ kind: 'already-exists' });
    latestMock.mockResolvedValue(ok(PLAN));

    await act(async () => {
      await result.current.completeBudgetPlan(GUEST_PLAN);
    });
    expect(result.current.status).toBe('ready');
  });

  it('invalid/error → 상태 유지 (게이트에서 에러 표시)', async () => {
    const { result } = await setupBudgetRequired();
    onboardingMock.mockResolvedValue({ kind: 'error' });

    let kind = '';
    await act(async () => {
      kind = await result.current.completeBudgetPlan(GUEST_PLAN);
    });
    expect(kind).toBe('error');
    expect(result.current.status).toBe('budget-required');
  });
});

describe('useMemberHome 완료 토글·가구 인원 (FR-501/503/504)', () => {
  function meal(id: string, completedAt: string | null = null): MealPlanMeal {
    return {
      id,
      planDate: '2026-07-08',
      mealType: 'breakfast',
      recipeName: `요리-${id}`,
      ingredients: [],
      completedAt,
    };
  }

  const TOGGLE_PLAN: MealPlanResponse = {
    ...PLAN,
    meals: [meal('m1', null), meal('m2', '2026-07-08T09:00:00Z')],
  };

  async function setupReady(plan: MealPlanResponse = TOGGLE_PLAN) {
    fetchMeMock.mockResolvedValue(ok(ME));
    latestMock.mockResolvedValue(ok(plan));
    const rendered = renderHook(() => useMemberHome());
    await waitFor(() => expect(rendered.result.current.status).toBe('ready'));
    return rendered;
  }

  it('가구 인원(households/me.size)을 노출한다', async () => {
    const { result } = await setupReady();
    await waitFor(() => expect(result.current.householdSize).toBe(4));
  });

  it('households/me 실패 시 householdSize=null (홈은 계속)', async () => {
    householdMock.mockResolvedValue(err(404, 'HOUSEHOLD_NOT_FOUND'));
    const { result } = await setupReady();
    expect(result.current.householdSize).toBeNull();
    expect(result.current.status).toBe('ready');
  });

  it('완료 설정: 낙관적 갱신 후 서버 MealOut 병합 (selectedDate 유지)', async () => {
    const { result } = await setupReady();
    act(() => result.current.selectDate('2026-07-08'));
    completionMock.mockResolvedValue(ok(meal('m1', '2026-07-08T10:00:00Z')));

    await act(() => result.current.toggleMealCompletion('m1'));

    expect(completionMock).toHaveBeenCalledWith('plan-1', 'm1', true);
    expect(result.current.plan?.meals.find((m) => m.id === 'm1')?.completedAt).toBe(
      '2026-07-08T10:00:00Z',
    );
    expect(result.current.viewModel?.selectedDate).toBe('2026-07-08');
    expect(result.current.pendingMealIds.size).toBe(0);
  });

  it('완료 해제: 이미 완료된 끼니 → completed=false 로 호출', async () => {
    const { result } = await setupReady();
    completionMock.mockResolvedValue(ok(meal('m2', null)));

    await act(() => result.current.toggleMealCompletion('m2'));

    expect(completionMock).toHaveBeenCalledWith('plan-1', 'm2', false);
    expect(result.current.plan?.meals.find((m) => m.id === 'm2')?.completedAt).toBeNull();
  });

  it('실패 시 이전 완료 상태로 롤백한다', async () => {
    const { result } = await setupReady();
    completionMock.mockResolvedValue(err(500, 'UNKNOWN'));

    await act(() => result.current.toggleMealCompletion('m1'));

    expect(result.current.plan?.meals.find((m) => m.id === 'm1')?.completedAt).toBeNull();
    expect(result.current.pendingMealIds.size).toBe(0);
  });

  it('연타 방지: 진행 중 재호출은 무시된다', async () => {
    const { result } = await setupReady();
    let resolveToggle: (value: ApiResult<MealPlanMeal>) => void = () => undefined;
    completionMock.mockImplementation(
      () => new Promise<ApiResult<MealPlanMeal>>((resolve) => (resolveToggle = resolve)),
    );

    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.toggleMealCompletion('m1');
    });
    await waitFor(() => expect(result.current.pendingMealIds.has('m1')).toBe(true));
    await act(() => result.current.toggleMealCompletion('m1'));
    expect(completionMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveToggle(ok(meal('m1', '2026-07-08T10:00:00Z')));
      await first;
    });
    expect(result.current.pendingMealIds.size).toBe(0);
  });

  it('plan 없음/없는 mealId → 아무 것도 하지 않는다', async () => {
    const { result } = await setupReady();
    await act(() => result.current.toggleMealCompletion('nope'));
    expect(completionMock).not.toHaveBeenCalled();
  });
});
