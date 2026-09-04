import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CycleStatusCard } from '@/features/cycle/CycleStatusCard';
import type { CycleStage, CycleState } from '@/features/cycle/types';
import type { OrderBlockedReason } from '@/features/order/types';
import { renderWithIntl } from '@/test/renderWithIntl';

function cycle(stage: CycleStage, reason: OrderBlockedReason | null = null): CycleState {
  return {
    enabled: stage !== 'paused',
    frequency: 'weekly',
    anchorWeekday: 0,
    timezone: 'Asia/Seoul',
    autoConfirm: true,
    cycleStart: '2026-09-06',
    cycleDays: 7,
    stage,
    nextRunAt: '2026-09-04T00:00:00Z',
    skippedCycleStart: null,
    weeklyLimit: { amount: '100000.00', currency: 'KRW' },
    mealPlan:
      stage === 'generated' || stage === 'delivered'
        ? { id: 'p1', status: 'ready', mealCount: 21, completedMealCount: 8 }
        : null,
    draftOrder:
      stage === 'drafted' || stage === 'awaiting_user'
        ? {
            id: 'o1',
            status: stage === 'drafted' ? 'draft' : 'awaiting_user',
            estimatedTotal: { amount: '50000.00', currency: 'KRW' },
            autoConfirmAt: '2026-09-05T00:00:00Z',
            blockedReason: reason,
            deliveryEta: null,
          }
        : null,
    currentOrder:
      stage === 'confirmed' || stage === 'delivered'
        ? {
            id: 'o1',
            status: 'confirmed',
            deliveryState: stage === 'delivered' ? 'delivered' : 'pending',
            deliveryEta: '2026-09-07T00:00:00Z',
            inboundAt: stage === 'delivered' ? '2026-09-07T00:00:00Z' : null,
            autoConfirmed: true,
          }
        : null,
    simulation: true,
  };
}

const actions = () => ({
  onApprove: vi.fn(),
  onViewOrder: vi.fn(),
  onSkip: vi.fn(),
  onCreateNow: vi.fn(),
  onViewMealPlan: vi.fn(),
  onViewFridge: vi.fn(),
  onGoSettings: vi.fn(),
  onCancelOrder: vi.fn(),
});

beforeEach(() => window.localStorage.clear());

describe('CycleStatusCard stage 단일 분기', () => {
  it.each([
    ['idle', '다음 사이클을 기다리고 있어요'],
    ['generating', '다음 주 식단 준비 중'],
    ['generated', '다음 주 식단이 나왔어요'],
    ['generate_failed', '다음 주 식단을 만들지 못했어요'],
    ['delivered', '이번 주 진행 중'],
    ['nothing_to_order', '이번 주는 냉장고로 충분해요'],
    ['skipped_user', '이번 주는 쉬어가요'],
    ['deferred_quota', '곧 준비할게요'],
    ['paused', '자동 사이클이 꺼져 있어요'],
  ] as const)('%s 상태를 서버 stage 그대로 표시한다', (stage, title) => {
    renderWithIntl(<CycleStatusCard cycle={cycle(stage)} {...actions()} />);
    expect(screen.getByText(title)).toBeInTheDocument();
  });

  it('drafted — 로컬 자동확정 시각 + 승인/보기/건너뛰기 1탭', () => {
    const callbacks = actions();
    renderWithIntl(
      <CycleStatusCard cycle={cycle('drafted')} notice="처리됨" {...callbacks} />,
    );
    expect(screen.getByText(/자동으로 확정돼요/)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('처리됨');
    fireEvent.click(screen.getByRole('button', { name: '승인하기' }));
    fireEvent.click(screen.getByRole('button', { name: '보기' }));
    fireEvent.click(screen.getByRole('button', { name: '이번 주 건너뛰기' }));
    expect(callbacks.onApprove).toHaveBeenCalledTimes(1);
    expect(callbacks.onViewOrder).toHaveBeenCalledTimes(1);
    expect(callbacks.onSkip).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['AUTO_CONFIRM_OFF', '승인하기', 'onApprove'],
    ['BUDGET_EXCEEDED', '그래도 승인하기', 'onApprove'],
    ['STORE_DISCONNECTED', '설정으로', 'onGoSettings'],
    ['MEALPLAN_OVER_BUDGET', '식단 다시 만들기', 'onCreateNow'],
    ['UNMATCHED_RATIO', '장바구니 확인', 'onViewOrder'],
    ['US_NO_PRICE', '장바구니 확인', 'onViewOrder'],
  ] as const)('awaiting_user %s 차단 사유 CTA를 매핑한다', (reason, label, callback) => {
    const callbacks = actions();
    renderWithIntl(
      <CycleStatusCard cycle={cycle('awaiting_user', reason)} {...callbacks} />,
    );
    fireEvent.click(screen.getByRole('button', { name: label }));
    expect(callbacks[callback]).toHaveBeenCalledTimes(1);
  });

  it('confirmed·nothing_to_order·paused 주요 CTA를 연결한다', () => {
    const confirmed = actions();
    const first = renderWithIntl(
      <CycleStatusCard cycle={cycle('confirmed')} {...confirmed} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '보기' }));
    fireEvent.click(screen.getByRole('button', { name: '주문 취소' }));
    expect(confirmed.onViewOrder).toHaveBeenCalledTimes(1);
    expect(confirmed.onCancelOrder).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/도착 예정/)).toBeInTheDocument();
    first.unmount();

    const fridge = actions();
    const second = renderWithIntl(
      <CycleStatusCard cycle={cycle('nothing_to_order')} {...fridge} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '냉장고 보기' }));
    expect(fridge.onViewFridge).toHaveBeenCalledTimes(1);
    second.unmount();

    const settings = actions();
    renderWithIntl(<CycleStatusCard cycle={cycle('paused')} {...settings} />);
    fireEvent.click(screen.getByRole('button', { name: '설정으로' }));
    expect(settings.onGoSettings).toHaveBeenCalledTimes(1);
  });

  it('delivered는 끼니 완료 수치를 표시한다', () => {
    renderWithIntl(<CycleStatusCard cycle={cycle('delivered')} {...actions()} />);
    expect(screen.getByText('8/21개 끼니 완료')).toBeInTheDocument();
  });

  it('generated/generate_failed CTA와 generating aria-busy를 노출한다', () => {
    const generated = actions();
    const first = renderWithIntl(
      <CycleStatusCard cycle={cycle('generated')} {...generated} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '식단 보기' }));
    expect(generated.onViewMealPlan).toHaveBeenCalledTimes(1);
    first.unmount();

    const failed = actions();
    const second = renderWithIntl(
      <CycleStatusCard cycle={cycle('generate_failed')} {...failed} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '직접 만들기' }));
    expect(failed.onCreateNow).toHaveBeenCalledTimes(1);
    second.unmount();

    renderWithIntl(<CycleStatusCard cycle={cycle('generating')} {...actions()} />);
    expect(screen.getByLabelText('주간 자동 사이클')).toHaveAttribute('aria-busy', 'true');
  });

  it('휴면 복귀 닫기는 cycleStart별 localStorage에 기록해 같은 카드만 숨긴다', () => {
    const callbacks = actions();
    renderWithIntl(
      <CycleStatusCard cycle={cycle('skipped_dormant')} {...callbacks} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '만들기' }));
    expect(callbacks.onCreateNow).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByText('이번 주 식단 만들까요?')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('cycle.dormantDismissed:2026-09-06')).toBe('1');
  });
});
