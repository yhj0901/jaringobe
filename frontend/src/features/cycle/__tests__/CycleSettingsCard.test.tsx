import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CycleSettingsCard } from '@/features/cycle/CycleSettingsCard';
import type { CycleHookState } from '@/features/cycle/useCycle';
import type { CycleState } from '@/features/cycle/types';
import { renderWithIntl } from '@/test/renderWithIntl';

const CYCLE: CycleState = {
  enabled: true,
  frequency: 'weekly',
  anchorWeekday: 0,
  timezone: 'Asia/Seoul',
  autoConfirm: true,
  cycleStart: '2026-09-06',
  cycleDays: 7,
  stage: 'idle',
  nextRunAt: null,
  skippedCycleStart: null,
  weeklyLimit: null,
  mealPlan: null,
  draftOrder: null,
  simulation: true,
};

const state: { current: CycleHookState } = { current: undefined as unknown as CycleHookState };
vi.mock('@/features/cycle/useCycle', () => ({ useCycle: () => state.current }));

function ready(overrides: Partial<CycleHookState> = {}): CycleHookState {
  return {
    status: 'ready',
    cycle: CYCLE,
    saving: false,
    errorCode: null,
    reload: vi.fn(),
    updateSettings: vi.fn().mockResolvedValue(true),
    skip: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.current = ready();
});

describe('CycleSettingsCard', () => {
  it('loading 스켈레톤과 error 재시도를 제공한다', () => {
    state.current = ready({ status: 'loading', cycle: null });
    const first = renderWithIntl(<CycleSettingsCard country="KR" />);
    expect(screen.getByLabelText('자동 주문')).toHaveAttribute('aria-busy', 'true');
    first.unmount();

    state.current = ready({ status: 'error', cycle: null });
    renderWithIntl(<CycleSettingsCard country="KR" />);
    expect(screen.getByRole('alert')).toHaveTextContent('불러오지 못했어요');
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(state.current.reload).toHaveBeenCalledTimes(1);
  });

  it('활성·주기·요일·자동확정을 부분 갱신한다', () => {
    renderWithIntl(<CycleSettingsCard country="KR" />);
    fireEvent.click(screen.getByRole('switch', { name: '사이클' }));
    fireEvent.click(screen.getByLabelText('주 2회'));
    fireEvent.click(screen.getByRole('button', { name: '화' }));
    fireEvent.click(screen.getByRole('switch', { name: '자동확정' }));
    expect(state.current.updateSettings).toHaveBeenNthCalledWith(1, { enabled: false });
    expect(state.current.updateSettings).toHaveBeenNthCalledWith(2, { frequency: 'biweekly' });
    expect(state.current.updateSettings).toHaveBeenNthCalledWith(3, { anchorWeekday: 2 });
    expect(state.current.updateSettings).toHaveBeenNthCalledWith(4, { autoConfirm: false });
    expect(screen.getByText(/알림 도달 여부와 무관/)).toBeInTheDocument();
    expect(screen.getByText(/Asia\/Seoul/)).toBeInTheDocument();
  });

  it('US·주 2회·수동 승인 보조 문구와 API 에러를 표시한다', () => {
    state.current = ready({
      cycle: { ...CYCLE, enabled: false, frequency: 'biweekly', autoConfirm: false },
      errorCode: 'RATE_LIMITED',
    });
    renderWithIntl(<CycleSettingsCard country="US" />);
    expect(screen.getByText('일시정지')).toBeInTheDocument();
    expect(screen.getByText(/주 1회를 권장/)).toBeInTheDocument();
    expect(screen.getByText(/12시간/)).toBeInTheDocument();
    expect(screen.getByText('항상 내가 승인할게요')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('요청이 많아요');
  });

  it('알 수 없는 에러 코드는 공통 폴백으로 표시한다', () => {
    state.current = ready({ errorCode: 'UNKNOWN' });
    renderWithIntl(<CycleSettingsCard country="KR" />);
    expect(screen.getByRole('alert')).toHaveTextContent('일시적인 오류가 발생했어요');
  });
});
