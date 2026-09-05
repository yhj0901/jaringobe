import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCycle } from '@/features/cycle/useCycle';
import type { CycleState } from '@/features/cycle/types';
import type { ApiResult } from '@/shared/api/client';

const fetchMock = vi.fn<() => Promise<ApiResult<CycleState>>>();
const putMock = vi.fn<() => Promise<ApiResult<CycleState>>>();
const skipMock = vi.fn<() => Promise<ApiResult<CycleState>>>();

vi.mock('@/features/cycle/api', () => ({
  fetchCycle: () => fetchMock(),
  putCycleSettings: () => putMock(),
  postCycleSkip: () => skipMock(),
}));

const CYCLE: CycleState = {
  enabled: true,
  frequency: 'weekly',
  anchorWeekday: 0,
  timezone: 'Asia/Seoul',
  autoConfirm: true,
  cycleStart: '2026-09-06',
  cycleDays: 7,
  stage: 'idle',
  nextRunAt: '2026-09-04T00:00:00Z',
  skippedCycleStart: null,
  weeklyLimit: { amount: '100000.00', currency: 'KRW' },
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
  fetchMock.mockResolvedValue(ok(CYCLE));
  putMock.mockResolvedValue(ok(CYCLE));
  skipMock.mockResolvedValue(ok({ ...CYCLE, stage: 'skipped_user' }));
});

describe('useCycle', () => {
  it('GET 성공과 reload를 반영한다', async () => {
    const { result } = renderHook(() => useCycle());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.cycle).toEqual(CYCLE);
    fetchMock.mockResolvedValue(ok({ ...CYCLE, stage: 'generated' }));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.cycle?.stage).toBe('generated'));
  });

  it('GET 401은 unauthenticated, 그 외 오류는 error로 닫힌다', async () => {
    fetchMock.mockResolvedValueOnce(fail(401, 'AUTH_REQUIRED'));
    const first = renderHook(() => useCycle());
    await waitFor(() => expect(first.result.current.status).toBe('unauthenticated'));
    first.unmount();

    fetchMock.mockResolvedValueOnce(fail(500, 'UNKNOWN'));
    const second = renderHook(() => useCycle());
    await waitFor(() => expect(second.result.current.status).toBe('error'));
    expect(second.result.current.errorCode).toBe('UNKNOWN');
  });

  it('설정 변경 성공은 서버 CycleState로 교체하고 실패는 에러 코드를 남긴다', async () => {
    const { result } = renderHook(() => useCycle());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    putMock.mockResolvedValueOnce(ok({ ...CYCLE, frequency: 'biweekly' }));
    await act(async () => {
      expect(await result.current.updateSettings({ frequency: 'biweekly' })).toBe(true);
    });
    expect(result.current.cycle?.frequency).toBe('biweekly');

    putMock.mockResolvedValueOnce(fail(429, 'RATE_LIMITED'));
    await act(async () => {
      expect(await result.current.updateSettings({ anchorWeekday: 3 })).toBe(false);
    });
    expect(result.current.errorCode).toBe('RATE_LIMITED');
  });

  it('건너뛰기 성공/실패를 처리한다', async () => {
    const { result } = renderHook(() => useCycle());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    await act(async () => {
      expect(await result.current.skip()).toBe(true);
    });
    expect(result.current.cycle?.stage).toBe('skipped_user');

    skipMock.mockResolvedValueOnce(fail(409, 'CYCLE_ALREADY_CONFIRMED'));
    await act(async () => {
      expect(await result.current.skip()).toBe(false);
    });
    expect(result.current.errorCode).toBe('CYCLE_ALREADY_CONFIRMED');
  });
});
