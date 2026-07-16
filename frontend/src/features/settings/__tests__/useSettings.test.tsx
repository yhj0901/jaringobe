import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useSettings } from '@/features/settings/useSettings';
import { fetchMe } from '@/features/auth/useSession';
import { postLogout } from '@/features/auth/logout';
import {
  fetchBudgetPlan,
  fetchHousehold,
  putBudgetPlan,
  putHouseholdMembers,
} from '@/features/household/api';
import {
  createMealPlan,
  fetchLatestMealPlan,
  regenerateMealPlan,
} from '@/features/mealplan/api';
import { fetchStoreConnections, putStoreConnection } from '@/features/store/api';
import { deleteDevice } from '@/features/notification/api';
import { useBridgeStore } from '@/shared/bridge/store';
import { VISITED_MARKER_KEY } from '@/shared/config/constants';
import { IntlWrapper } from '@/test/renderWithIntl';
import { stubAppEnvironment } from '@/test/appEnv';
import type { MealPlanResponse } from '@/features/mealplan/types';
import type { ApiResult } from '@/shared/api/client';

vi.mock('@/features/auth/useSession', () => ({ fetchMe: vi.fn() }));
vi.mock('@/features/auth/logout', () => ({ postLogout: vi.fn() }));
vi.mock('@/features/household/api', () => ({
  fetchBudgetPlan: vi.fn(),
  fetchHousehold: vi.fn(),
  putHouseholdMembers: vi.fn(),
  putBudgetPlan: vi.fn(),
}));
vi.mock('@/features/mealplan/api', () => ({
  fetchLatestMealPlan: vi.fn(),
  createMealPlan: vi.fn(),
  regenerateMealPlan: vi.fn(),
}));
vi.mock('@/features/store/api', () => ({
  fetchStoreConnections: vi.fn(),
  putStoreConnection: vi.fn(),
}));
vi.mock('@/features/notification/api', () => ({ deleteDevice: vi.fn() }));

const fetchMeMock = vi.mocked(fetchMe);
const logoutMock = vi.mocked(postLogout);
const householdMock = vi.mocked(fetchHousehold);
const budgetPlanGetMock = vi.mocked(fetchBudgetPlan);
const putMembersMock = vi.mocked(putHouseholdMembers);
const putBudgetMock = vi.mocked(putBudgetPlan);
const latestMock = vi.mocked(fetchLatestMealPlan);
const createMock = vi.mocked(createMealPlan);
const regenerateMock = vi.mocked(regenerateMealPlan);
const storesMock = vi.mocked(fetchStoreConnections);
const putStoreMock = vi.mocked(putStoreConnection);
const deleteDeviceMock = vi.mocked(deleteDevice);

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function err(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

const ME = {
  id: 'u1',
  nickname: '자린이',
  email: 'me@example.com',
  profileImageUrl: null,
  locale: 'ko',
  country: 'KR',
  currency: 'KRW',
  onboardingCompleted: true,
  hasBudgetPlan: true,
};

const MEMBERS = [
  { memberType: 'adult_m' as const, age: 35 },
  { memberType: 'adult_f' as const, age: 33 },
];

const PLAN = {
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
  meals: [],
  notes: [],
} as unknown as MealPlanResponse;

/** GET /budget/plans 현재값 (api-spec 2-2 v1.3.1) — 서버 저장 방향·선호·락 포함 */
const BUDGET_PLAN_DETAIL = {
  id: 'b1',
  householdSize: 2,
  budget: { amount: '420000.00', currency: 'KRW' as const },
  mealDirection: 'hearty' as const,
  source: 'onboarding' as const,
  createdAt: '2026-07-09T00:00:00Z',
  locked: true,
  cuisines: ['japanese' as const],
};

const CONNECTIONS = {
  connections: [
    { store: 'kurly' as const, status: 'connected' as const, connectedAt: '2026-07-10T00:00:00Z' },
    { store: 'coupang' as const, status: 'disconnected' as const, connectedAt: null },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  return <IntlWrapper>{children}</IntlWrapper>;
}

function seedHappyPath() {
  fetchMeMock.mockResolvedValue(ok(ME));
  householdMock.mockResolvedValue(ok({ members: MEMBERS, size: 2 }));
  budgetPlanGetMock.mockResolvedValue(ok(BUDGET_PLAN_DETAIL));
  latestMock.mockResolvedValue(ok(PLAN));
  storesMock.mockResolvedValue(ok(CONNECTIONS));
}

async function renderReady() {
  const view = renderHook(() => useSettings(), { wrapper });
  await waitFor(() => expect(view.result.current.status).toBe('ready'));
  return view;
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe('useSettings 조회 분기 (ui-design 9장)', () => {
  it('users/me 401 → unauthenticated', async () => {
    fetchMeMock.mockResolvedValue(err(401, 'AUTH_REQUIRED'));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));
    expect(householdMock).not.toHaveBeenCalled();
  });

  it('users/me 5xx → error', async () => {
    fetchMeMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('정상 조회 → 구성원·예산 현재값(GET budget/plans 우선)·planId·연동 맵 (FR-402/404)', async () => {
    seedHappyPath();
    const { result } = await renderReady();

    expect(result.current.user?.nickname).toBe('자린이');
    expect(result.current.members).toEqual(MEMBERS);
    // 예산 금액은 latest 요약(700,000)이 아닌 GET budget/plans 실제값(420,000)
    expect(result.current.budget).toEqual({ amount: '420000.00', currency: 'KRW' });
    expect(result.current.planId).toBe('plan-1');
    // 방향·선호·락은 서버 현재값으로 확정 (api-spec 2-2)
    expect(result.current.profile).toEqual({
      direction: 'hearty',
      cuisines: ['japanese'],
      locked: true,
      known: true,
    });
    // 응답에 없는 스토어(ssg/naver)는 disconnected 로 채운다
    expect(result.current.connections).toEqual({
      kurly: true,
      coupang: false,
      ssg: false,
      naver: false,
    });
  });

  it('household 404 + budget 404 + latest 404 → 설정 전 상태로 ready (FR-402)', async () => {
    seedHappyPath();
    householdMock.mockResolvedValue(err(404, 'HOUSEHOLD_NOT_FOUND'));
    budgetPlanGetMock.mockResolvedValue(err(404, 'BUDGET_PLAN_NOT_FOUND'));
    latestMock.mockResolvedValue(err(404, 'MEALPLAN_NOT_FOUND'));
    const { result } = await renderReady();

    expect(result.current.members).toBeNull();
    expect(result.current.budget).toBeNull();
    expect(result.current.planId).toBeNull();
    expect(result.current.profile.known).toBe(false);
  });

  it('budget 404 + latest 있음 → latest 요약 금액으로 폴백 (기존 폴백 유지)', async () => {
    seedHappyPath();
    budgetPlanGetMock.mockResolvedValue(err(404, 'BUDGET_PLAN_NOT_FOUND'));
    const { result } = await renderReady();

    expect(result.current.budget).toEqual({ amount: '700000.00', currency: 'KRW' });
    expect(result.current.profile.known).toBe(false);
  });

  it('budget 5xx → error', async () => {
    seedHappyPath();
    budgetPlanGetMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('household 5xx → error', async () => {
    seedHappyPath();
    householdMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('latest 5xx → error', async () => {
    seedHappyPath();
    latestMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('stores 조회 실패 → error + reload 로 재시도', async () => {
    seedHappyPath();
    storesMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    const { result } = renderHook(() => useSettings(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe('error'));

    storesMock.mockResolvedValue(ok(CONNECTIONS));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.status).toBe('ready'));
  });
});

describe('useSettings 저장 동작 (FR-402)', () => {
  it('saveHousehold 성공 → PUT 응답 구성원 반영', async () => {
    seedHappyPath();
    const nextMembers = [...MEMBERS, { memberType: 'child' as const, age: 9 }];
    putMembersMock.mockResolvedValue(ok({ members: nextMembers, size: 3 }));
    const { result } = await renderReady();

    let saved = false;
    await act(async () => {
      saved = await result.current.saveHousehold(nextMembers);
    });
    expect(saved).toBe(true);
    expect(putMembersMock).toHaveBeenCalledWith(nextMembers);
    expect(result.current.members).toEqual(nextMembers);
  });

  it('saveHousehold 실패 → false + 기존 구성원 유지', async () => {
    seedHappyPath();
    putMembersMock.mockResolvedValue(err(422, 'VALIDATION_ERROR'));
    const { result } = await renderReady();

    let saved = true;
    await act(async () => {
      saved = await result.current.saveHousehold(MEMBERS);
    });
    expect(saved).toBe(false);
    expect(result.current.members).toEqual(MEMBERS);
  });

  it('saveBudget → 서버 현재값(방향·선호) 병합 upsert — 예산만 수정해도 보존 (FR-402)', async () => {
    seedHappyPath();
    putBudgetMock.mockResolvedValue(
      ok({
        id: 'b1',
        householdSize: 2,
        budget: { amount: '520000.00', currency: 'KRW' },
        mealDirection: 'hearty',
        source: 'onboarding',
        createdAt: '2026-07-10T00:00:00Z',
      }),
    );
    const { result } = await renderReady();

    let saved = false;
    await act(async () => {
      saved = await result.current.saveBudget('520000', false);
    });
    expect(saved).toBe(true);
    // 병합 베이스 = GET /budget/plans 서버값 (hearty·japanese 보존, locked 만 변경)
    expect(putBudgetMock).toHaveBeenCalledWith({
      householdSize: 2,
      budget: { amount: '520000', currency: 'KRW' },
      mealDirection: 'hearty',
      locked: false,
      cuisines: ['japanese'],
    });
    // 요약 예산은 PUT 응답으로 갱신
    expect(result.current.budget).toEqual({ amount: '520000.00', currency: 'KRW' });
    expect(result.current.profile.locked).toBe(false);
  });

  it('savePreference → 방향·선호 갱신 + 예산은 서버 현재값 금액 유지', async () => {
    seedHappyPath();
    putBudgetMock.mockResolvedValue(
      ok({
        id: 'b1',
        householdSize: 2,
        budget: { amount: '420000.00', currency: 'KRW' },
        mealDirection: 'kids',
        source: 'onboarding',
        createdAt: '2026-07-10T00:00:00Z',
      }),
    );
    const { result } = await renderReady();

    await act(async () => {
      await result.current.savePreference(['korean', 'salad'], 'kids');
    });
    expect(putBudgetMock).toHaveBeenCalledWith({
      householdSize: 2,
      budget: { amount: '420000.00', currency: 'KRW' },
      mealDirection: 'kids',
      locked: true,
      cuisines: ['korean', 'salad'],
    });
    expect(result.current.profile).toEqual({
      direction: 'kids',
      cuisines: ['korean', 'salad'],
      locked: true,
      known: true,
    });
  });

  it('savePreference — 예산 현재값이 없으면(404) 인원 기반 권장값 폴백 (CWE-20 범위 준수)', async () => {
    seedHappyPath();
    budgetPlanGetMock.mockResolvedValue(err(404, 'BUDGET_PLAN_NOT_FOUND'));
    latestMock.mockResolvedValue(err(404, 'MEALPLAN_NOT_FOUND'));
    putBudgetMock.mockResolvedValue(
      ok({
        id: 'b1',
        householdSize: 2,
        budget: { amount: '260000.00', currency: 'KRW' },
        mealDirection: 'diet',
        source: 'onboarding',
        createdAt: '2026-07-10T00:00:00Z',
      }),
    );
    const { result } = await renderReady();

    await act(async () => {
      await result.current.savePreference([], 'diet');
    });
    // 2인 × 권장 130,000 = 260,000
    expect(putBudgetMock.mock.calls[0]?.[0]?.budget).toEqual({
      amount: '260000',
      currency: 'KRW',
    });
  });

  it('saveBudget 실패 → false', async () => {
    seedHappyPath();
    putBudgetMock.mockResolvedValue(err(422, 'VALIDATION_ERROR'));
    const { result } = await renderReady();

    let saved = true;
    await act(async () => {
      saved = await result.current.saveBudget('520000', true);
    });
    expect(saved).toBe(false);
  });
});

describe('useSettings 스토어 토글 (FR-404)', () => {
  it('연동 성공 → 연동 맵 갱신', async () => {
    seedHappyPath();
    putStoreMock.mockResolvedValue(ok({}));
    const { result } = await renderReady();

    let done = false;
    await act(async () => {
      done = await result.current.toggleStore('coupang', true);
    });
    expect(done).toBe(true);
    expect(putStoreMock).toHaveBeenCalledWith('coupang', true);
    expect(result.current.connections?.coupang).toBe(true);
  });

  it('해제 실패 → false + 상태 유지', async () => {
    seedHappyPath();
    putStoreMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const { result } = await renderReady();

    let done = true;
    await act(async () => {
      done = await result.current.toggleStore('kurly', false);
    });
    expect(done).toBe(false);
    expect(result.current.connections?.kurly).toBe(true);
  });
});

describe('useSettings 재생성·로그아웃 (FR-401/403)', () => {
  it('latest 있음 → regenerate 호출 (scope=all 재사용)', async () => {
    seedHappyPath();
    regenerateMock.mockResolvedValue(ok(PLAN));
    const { result } = await renderReady();

    let outcome: string | null = null;
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('ok');
    expect(regenerateMock).toHaveBeenCalledWith('plan-1');
    expect(createMock).not.toHaveBeenCalled();
  });

  it('latest 없음 → 생성 폴백 (선호 라벨 preferences 전달)', async () => {
    seedHappyPath();
    latestMock.mockResolvedValue(err(404, 'MEALPLAN_NOT_FOUND'));
    putBudgetMock.mockResolvedValue(
      ok({
        id: 'b1',
        householdSize: 2,
        budget: { amount: '260000.00', currency: 'KRW' },
        mealDirection: 'health',
        source: 'onboarding',
        createdAt: '2026-07-10T00:00:00Z',
      }),
    );
    createMock.mockResolvedValue(ok(PLAN, 201));
    const { result } = await renderReady();

    await act(async () => {
      await result.current.savePreference(['korean'], 'health');
    });
    let outcome: string | null = null;
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('ok');
    expect(createMock).toHaveBeenCalledWith({
      days: 7,
      mealsPerDay: 3,
      allergies: [],
      preferences: ['한식'],
    });
  });

  it('재생성 429 → rate-limited / 5xx → failed', async () => {
    seedHappyPath();
    const { result } = await renderReady();

    regenerateMock.mockResolvedValueOnce(err(429, 'RATE_LIMITED'));
    let outcome: string | null = null;
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('rate-limited');

    regenerateMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('failed');
  });

  it('재생성 409 MEALPLAN_REGENERATE_EMPTY → 기존 생성 폴백으로 신규 POST 전환 (api-spec 3-5 v1.5.1)', async () => {
    seedHappyPath();
    regenerateMock.mockResolvedValueOnce(err(409, 'MEALPLAN_REGENERATE_EMPTY'));
    createMock.mockResolvedValue(ok(PLAN, 201));
    const { result } = await renderReady();

    let outcome: string | null = null;
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('ok');
    expect(regenerateMock).toHaveBeenCalledWith('plan-1');
    // 신규 생성 — 프로필 선호 라벨(일식)로 POST /mealplans (latest 없음 폴백과 동일 경로)
    expect(createMock).toHaveBeenCalledWith({
      days: 7,
      mealsPerDay: 3,
      allergies: [],
      preferences: ['일식'],
    });
    expect(result.current.generating).toBe(false);
  });

  it('재생성 409 MEALPLAN_REGENERATE_EMPTY 후 신규 생성도 실패하면 failed', async () => {
    seedHappyPath();
    regenerateMock.mockResolvedValueOnce(err(409, 'MEALPLAN_REGENERATE_EMPTY'));
    createMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    const { result } = await renderReady();

    let outcome: string | null = null;
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('failed');
  });

  it('재생성 409 MEALPLAN_GENERATING → ok (홈에서 진행 중 폴링 합류, ui-design 12장)', async () => {
    seedHappyPath();
    regenerateMock.mockResolvedValueOnce(err(409, 'MEALPLAN_GENERATING'));
    const { result } = await renderReady();

    let outcome: string | null = null;
    await act(async () => {
      outcome = await result.current.regenerate();
    });
    expect(outcome).toBe('ok');
  });

  it('앱 내 로그아웃 → DELETE /notifications/devices/{token} 선행 후 POST logout (ui-design 12장)', async () => {
    seedHappyPath();
    logoutMock.mockResolvedValue(ok(undefined, 204));
    deleteDeviceMock.mockResolvedValue(ok(undefined, 204));
    const app = stubAppEnvironment();
    useBridgeStore.setState({ deviceToken: 'ExponentPushToken[abc]' });
    try {
      const { result } = await renderReady();
      let done = false;
      await act(async () => {
        done = await result.current.logout();
      });
      expect(done).toBe(true);
      expect(deleteDeviceMock).toHaveBeenCalledWith('ExponentPushToken[abc]');
      // 토큰 해제가 로그아웃보다 먼저 (선행)
      const deleteOrder = deleteDeviceMock.mock.invocationCallOrder[0] ?? 0;
      const logoutOrder = logoutMock.mock.invocationCallOrder[0] ?? 0;
      expect(deleteOrder).toBeLessThan(logoutOrder);
    } finally {
      useBridgeStore.getState().reset();
      app.restore();
    }
  });

  it('앱 내 토큰 해제 실패해도 로그아웃은 진행한다 / 토큰 없으면 DELETE 생략', async () => {
    seedHappyPath();
    logoutMock.mockResolvedValue(ok(undefined, 204));
    deleteDeviceMock.mockResolvedValue(err(500, 'UNKNOWN'));
    const app = stubAppEnvironment();
    useBridgeStore.setState({ deviceToken: 'ExponentPushToken[abc]' });
    try {
      const { result } = await renderReady();
      let done = false;
      await act(async () => {
        done = await result.current.logout();
      });
      expect(done).toBe(true);

      // 토큰 미보유 — DELETE 생략
      deleteDeviceMock.mockClear();
      useBridgeStore.getState().reset();
      await act(async () => {
        await result.current.logout();
      });
      expect(deleteDeviceMock).not.toHaveBeenCalled();
    } finally {
      useBridgeStore.getState().reset();
      app.restore();
    }
  });

  it('웹(브라우저) 로그아웃은 토큰 해제 없이 진행한다', async () => {
    seedHappyPath();
    logoutMock.mockResolvedValue(ok(undefined, 204));
    useBridgeStore.setState({ deviceToken: 'ExponentPushToken[abc]' });
    try {
      const { result } = await renderReady();
      await act(async () => {
        await result.current.logout();
      });
      expect(deleteDeviceMock).not.toHaveBeenCalled();
    } finally {
      useBridgeStore.getState().reset();
    }
  });

  it('로그아웃 204 → visited 마커 기록 + true (FR-401)', async () => {
    seedHappyPath();
    logoutMock.mockResolvedValue(ok(undefined, 204));
    const { result } = await renderReady();

    let done = false;
    await act(async () => {
      done = await result.current.logout();
    });
    expect(done).toBe(true);
    expect(window.localStorage.getItem(VISITED_MARKER_KEY)).toBe('1');
  });

  it('로그아웃 401(이미 만료) → 성공 취급 + 마커 기록', async () => {
    seedHappyPath();
    logoutMock.mockResolvedValue(err(401, 'AUTH_REQUIRED'));
    const { result } = await renderReady();

    let done = false;
    await act(async () => {
      done = await result.current.logout();
    });
    expect(done).toBe(true);
    expect(window.localStorage.getItem(VISITED_MARKER_KEY)).toBe('1');
  });

  it('로그아웃 네트워크 실패 → false + 마커 미기록', async () => {
    seedHappyPath();
    logoutMock.mockResolvedValue(err(0, 'NETWORK_ERROR'));
    const { result } = await renderReady();

    let done = true;
    await act(async () => {
      done = await result.current.logout();
    });
    expect(done).toBe(false);
    expect(window.localStorage.getItem(VISITED_MARKER_KEY)).toBeNull();
  });
});
