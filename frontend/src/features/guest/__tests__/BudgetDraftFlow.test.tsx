import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { BudgetDraftFlow } from '@/features/guest/BudgetDraftFlow';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('BudgetDraftFlow (FR-104)', () => {
  it('open=false 이면 렌더하지 않는다', () => {
    renderWithIntl(
      <BudgetDraftFlow open={false} onClose={() => undefined} onComplete={() => undefined} />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('3스텝(인원 → 프리셋 예산 → 식단 방향)을 완료하면 plan 을 전달한다', () => {
    const onComplete = vi.fn();
    renderWithIntl(
      <BudgetDraftFlow open onClose={() => undefined} onComplete={onComplete} />,
    );

    // 1단계: 인원 2 → 4
    fireEvent.click(screen.getByLabelText('인원 늘리기'));
    fireEvent.click(screen.getByLabelText('인원 늘리기'));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));

    // 2단계: 70만원 프리셋 선택
    fireEvent.click(screen.getByRole('radio', { name: '₩700,000' }));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));

    // 3단계: 아이 입맛
    fireEvent.click(screen.getByRole('button', { name: '아이 입맛' }));

    expect(onComplete).toHaveBeenCalledWith({
      householdSize: 4,
      amount: '700000',
      currency: 'KRW',
      mealDirection: 'kids',
    });
  });

  it('직접 입력 금액이 범위를 벗어나면 오류를 표시하고 진행하지 않는다', () => {
    const onComplete = vi.fn();
    renderWithIntl(
      <BudgetDraftFlow open onClose={() => undefined} onComplete={onComplete} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '다음' }));

    fireEvent.change(screen.getByLabelText(/직접 입력/), { target: { value: '10000' } });
    fireEvent.click(screen.getByRole('button', { name: '다음' }));

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('유효한 직접 입력 금액으로 완료할 수 있다', () => {
    const onComplete = vi.fn();
    renderWithIntl(
      <BudgetDraftFlow open onClose={() => undefined} onComplete={onComplete} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.change(screen.getByLabelText(/직접 입력/), { target: { value: '450000' } });
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.click(screen.getByRole('button', { name: '건강식' }));

    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({ amount: '450000', currency: 'KRW', mealDirection: 'health' }),
    );
  });

  it('예산을 선택하지 않고 다음을 누르면 오류를 표시한다', () => {
    renderWithIntl(
      <BudgetDraftFlow open onClose={() => undefined} onComplete={() => undefined} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('en 로캘은 USD 프리셋을 노출한다 (US-107)', () => {
    renderWithIntl(
      <BudgetDraftFlow open onClose={() => undefined} onComplete={() => undefined} />,
      'en',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('radio', { name: '$300.00' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '$1,000.00' })).toBeInTheDocument();
  });

  it('이전 버튼으로 단계를 되돌릴 수 있다', () => {
    renderWithIntl(
      <BudgetDraftFlow open onClose={() => undefined} onComplete={() => undefined} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    expect(screen.getByText('한 달 식비 예산은 얼마인가요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '이전' }));
    expect(screen.getByText('몇 명이 함께 식사하나요?')).toBeInTheDocument();
  });

  it('ESC 키로 닫힌다', () => {
    const onClose = vi.fn();
    renderWithIntl(
      <BudgetDraftFlow open onClose={onClose} onComplete={() => undefined} />,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
