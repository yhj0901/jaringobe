import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { BudgetPlanGate } from '@/features/mealplan/BudgetPlanGate';
import { renderWithIntl } from '@/test/renderWithIntl';

/** BudgetDraftFlow 3스텝을 끝까지 진행 (인원 기본 2 → 첫 프리셋 → 건강식) */
function completeDraftFlow() {
  fireEvent.click(screen.getByRole('button', { name: '예산안 만들기' }));
  expect(screen.getByText('내 예산안 만들기')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '다음' }));
  fireEvent.click(screen.getAllByRole('radio')[0] as HTMLElement);
  fireEvent.click(screen.getByRole('button', { name: '다음' }));
  fireEvent.click(screen.getByRole('button', { name: '건강식' }));
}

describe('BudgetPlanGate (FR-207)', () => {
  it('BudgetDraftFlow 재사용 → 완료 시 onComplete 에 예산안을 넘긴다', async () => {
    const onComplete = vi.fn().mockResolvedValue('created');
    renderWithIntl(<BudgetPlanGate onComplete={onComplete} />);

    expect(screen.getByText('먼저 예산안을 만들어 주세요')).toBeInTheDocument();
    completeDraftFlow();

    await waitFor(() =>
      expect(onComplete).toHaveBeenCalledWith({
        householdSize: 2,
        amount: '300000',
        currency: 'KRW',
        mealDirection: 'health',
      }),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('invalid/error 결과면 공통 에러 배너를 표시한다', async () => {
    const onComplete = vi.fn().mockResolvedValue('error');
    renderWithIntl(<BudgetPlanGate onComplete={onComplete} />);

    completeDraftFlow();
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('일시적인 오류가 발생했어요');
  });
});
