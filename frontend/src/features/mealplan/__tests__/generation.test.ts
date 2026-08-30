import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  isDisplayableStatus,
  pollMealPlan,
  runGenerationFlow,
  startGeneration,
} from '@/features/mealplan/generation';
import { fetchLatestMealPlan, fetchMealPlan } from '@/features/mealplan/api';
import type { MealPlanResponse, MealPlanStatus } from '@/features/mealplan/types';
import type { ApiResult } from '@/shared/api/client';

vi.mock('@/features/mealplan/api', () => ({
  fetchLatestMealPlan: vi.fn(),
  fetchMealPlan: vi.fn(),
}));

const fetchPlanMock = vi.mocked(fetchMealPlan);
const latestMock = vi.mocked(fetchLatestMealPlan);

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function err(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

function plan(status: MealPlanStatus, id = 'plan-1'): MealPlanResponse {
  const done = status === 'ready' || status === 'over_budget';
  return {
    id,
    status,
    region: 'KR',
    currency: 'KRW',
    periodStart: done ? '2026-07-08' : null,
    periodEnd: done ? '2026-07-14' : null,
    budgetSummary: done
      ? {
          budget: { amount: '700000.00', currency: 'KRW' },
          plannedCost: { amount: '612300.00', currency: 'KRW' },
          remaining: { amount: '87700.00', currency: 'KRW' },
          withinBudget: status === 'ready',
        }
      : null,
    meals: [],
    notes: status === 'failed' ? ['GENERATION_FAILED'] : [],
  };
}

/** 대기 시간을 기록만 하는 즉시 sleep (테스트 주입) */
function recordingSleep(): { sleep: (ms: number) => Promise<void>; delays: number[] } {
  const delays: number[] = [];
  return {
    delays,
    sleep: (ms: number) => {
      delays.push(ms);
      return Promise.resolve();
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('pollMealPlan (ui-design 12장 — 3초 폴링·5초 백오프·최대 3분)', () => {
  it('첫 조회가 ready 면 즉시 completed (대기 없음)', async () => {
    const { sleep, delays } = recordingSleep();
    fetchPlanMock.mockResolvedValue(ok(plan('ready')));

    const outcome = await pollMealPlan('plan-1', { sleep });
    expect(outcome).toEqual({ kind: 'completed', plan: plan('ready') });
    expect(delays).toEqual([]);
  });

  it('over_budget 도 완료로 취급한다', async () => {
    const { sleep } = recordingSleep();
    fetchPlanMock.mockResolvedValue(ok(plan('over_budget')));
    const outcome = await pollMealPlan('plan-1', { sleep });
    expect(outcome.kind).toBe('completed');
  });

  it('processing → 3초 간격 폴링, backoffAfter 초과 시 5초 백오프 (기본 상수)', async () => {
    const { sleep, delays } = recordingSleep();
    // 12회 processing 후 ready — 기본 backoffAfter=10 이므로 11번째부터 5초
    for (let i = 0; i < 12; i += 1) fetchPlanMock.mockResolvedValueOnce(ok(plan('processing')));
    fetchPlanMock.mockResolvedValueOnce(ok(plan('ready')));

    const outcome = await pollMealPlan('plan-1', { sleep });
    expect(outcome.kind).toBe('completed');
    expect(delays.slice(0, 10)).toEqual(Array<number>(10).fill(3_000));
    expect(delays.slice(10)).toEqual([5_000, 5_000]);
  });

  it('status=failed → failed', async () => {
    const { sleep } = recordingSleep();
    fetchPlanMock.mockResolvedValue(ok(plan('failed')));
    const outcome = await pollMealPlan('plan-1', { sleep });
    expect(outcome).toEqual({ kind: 'failed' });
  });

  it('일시 오류(5xx/네트워크)는 폴링을 계속한다', async () => {
    const { sleep } = recordingSleep();
    fetchPlanMock
      .mockResolvedValueOnce(err(500, 'UNKNOWN'))
      .mockResolvedValueOnce(err(0, 'NETWORK_ERROR'))
      .mockResolvedValueOnce(ok(plan('ready')));

    const outcome = await pollMealPlan('plan-1', { sleep });
    expect(outcome.kind).toBe('completed');
    expect(fetchPlanMock).toHaveBeenCalledTimes(3);
  });

  it('401/403/404 는 지속 불가 — failed', async () => {
    const { sleep } = recordingSleep();
    for (const status of [401, 403, 404]) {
      fetchPlanMock.mockReset();
      fetchPlanMock.mockResolvedValue(err(status, 'ANY'));
      const outcome = await pollMealPlan('plan-1', { sleep });
      expect(outcome).toEqual({ kind: 'failed' });
      expect(fetchPlanMock).toHaveBeenCalledTimes(1);
    }
  });

  it('기본 sleep(setTimeout) 경로 — 3초 후 재조회한다', async () => {
    vi.useFakeTimers();
    try {
      fetchPlanMock
        .mockResolvedValueOnce(ok(plan('processing')))
        .mockResolvedValueOnce(ok(plan('ready')));

      const pending = pollMealPlan('plan-1');
      await vi.advanceTimersByTimeAsync(3_000);
      const outcome = await pending;
      expect(outcome.kind).toBe('completed');
      expect(fetchPlanMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('최대 시간 초과 → timeout ("완료되면 알려드릴게요" 안내 분기)', async () => {
    const { sleep, delays } = recordingSleep();
    fetchPlanMock.mockResolvedValue(ok(plan('processing')));

    const outcome = await pollMealPlan('plan-1', {
      sleep,
      intervalMs: 100,
      backoffMs: 200,
      backoffAfter: 2,
      maxDurationMs: 450,
    });
    // 대기 계획: 100, 100, 200 (누적 400) → 다음 200 은 450 초과 → timeout
    expect(outcome).toEqual({ kind: 'timeout' });
    expect(delays).toEqual([100, 100, 200]);
    expect(fetchPlanMock).toHaveBeenCalledTimes(4);
  });
});

describe('startGeneration / runGenerationFlow (202·409 합류·429)', () => {
  it('202 → 해당 id 로 시작', async () => {
    const begin = vi.fn().mockResolvedValue(ok({ id: 'plan-9', status: 'processing' }, 202));
    const start = await startGeneration(begin);
    expect(start).toEqual({ kind: 'started', planId: 'plan-9' });
  });

  it('429 → rate-limited', async () => {
    const begin = vi.fn().mockResolvedValue(err(429, 'RATE_LIMITED'));
    expect(await startGeneration(begin)).toEqual({ kind: 'rate-limited' });
    expect(await runGenerationFlow(begin)).toEqual({ kind: 'rate-limited' });
  });

  it('409 MEALPLAN_GENERATING → 진행 중 최신 플랜에 폴링 합류', async () => {
    const begin = vi.fn().mockResolvedValue(err(409, 'MEALPLAN_GENERATING'));
    latestMock.mockResolvedValue(ok(plan('processing', 'plan-live')));
    const start = await startGeneration(begin);
    expect(start).toEqual({ kind: 'started', planId: 'plan-live' });
  });

  it('409 합류 시점에 최신 플랜이 이미 완료(ready/over_budget)면 completed (BUG-007)', async () => {
    const begin = vi.fn().mockResolvedValue(err(409, 'MEALPLAN_GENERATING'));

    latestMock.mockResolvedValue(ok(plan('ready')));
    expect(await startGeneration(begin)).toEqual({ kind: 'completed', plan: plan('ready') });

    latestMock.mockResolvedValue(ok(plan('over_budget')));
    expect(await startGeneration(begin)).toEqual({ kind: 'completed', plan: plan('over_budget') });
  });

  it('409 합류 completed 는 runGenerationFlow 에서 폴링 없이 그대로 반환한다 (BUG-007)', async () => {
    const begin = vi.fn().mockResolvedValue(err(409, 'MEALPLAN_GENERATING'));
    latestMock.mockResolvedValue(ok(plan('ready')));

    const outcome = await runGenerationFlow(begin, { sleep: () => Promise.resolve() });
    expect(outcome).toEqual({ kind: 'completed', plan: plan('ready') });
    expect(fetchPlanMock).not.toHaveBeenCalled(); // 이미 완료 — 폴링 불필요
  });

  it('409 인데 최신 플랜이 failed 이거나 조회 불가면 기존대로 failed', async () => {
    const begin = vi.fn().mockResolvedValue(err(409, 'MEALPLAN_GENERATING'));

    latestMock.mockResolvedValue(ok(plan('failed')));
    expect(await startGeneration(begin)).toEqual({ kind: 'failed' });

    latestMock.mockResolvedValue(err(404, 'MEALPLAN_NOT_FOUND'));
    expect(await startGeneration(begin)).toEqual({ kind: 'failed' });
  });

  it('그 외 실패(5xx 등) → failed', async () => {
    const begin = vi.fn().mockResolvedValue(err(500, 'UNKNOWN'));
    expect(await startGeneration(begin)).toEqual({ kind: 'failed' });
    expect(await runGenerationFlow(begin)).toEqual({ kind: 'failed' });
  });

  it('runGenerationFlow: 202 → 폴링 → completed', async () => {
    const begin = vi.fn().mockResolvedValue(ok({ id: 'plan-1', status: 'processing' }, 202));
    fetchPlanMock.mockResolvedValue(ok(plan('ready')));
    const outcome = await runGenerationFlow(begin, { sleep: () => Promise.resolve() });
    expect(outcome.kind).toBe('completed');
  });
});

describe('isDisplayableStatus', () => {
  it('ready/over_budget 만 true', () => {
    expect(isDisplayableStatus('ready')).toBe(true);
    expect(isDisplayableStatus('over_budget')).toBe(true);
    expect(isDisplayableStatus('processing')).toBe(false);
    expect(isDisplayableStatus('failed')).toBe(false);
  });
});
