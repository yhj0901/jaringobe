import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { EmptyPlanHero } from '@/features/mealplan/EmptyPlanHero';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('EmptyPlanHero (FR-202)', () => {
  it('예산 락 히어로 + "내 식단 만들기" CTA 를 렌더한다', () => {
    const onCreate = vi.fn();
    renderWithIntl(<EmptyPlanHero onCreate={onCreate} />);

    expect(screen.getByText('예산 락')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '내 식단 만들기' }));
    expect(onCreate).toHaveBeenCalledTimes(1);
    // 예산 미상이면 금액 영역 미노출
    expect(screen.queryByText('내 월 예산')).not.toBeInTheDocument();
  });

  it('예산을 알면 금액을 로캘 포맷으로 표시한다', () => {
    renderWithIntl(
      <EmptyPlanHero budget={{ amount: '500000.00', currency: 'KRW' }} onCreate={vi.fn()} />,
    );
    expect(screen.getByText('내 월 예산')).toBeInTheDocument();
    expect(screen.getByText('₩500,000')).toBeInTheDocument();
  });

  it('busy=true 면 CTA 가 비활성화된다 (연타 방지)', () => {
    const onCreate = vi.fn();
    renderWithIntl(<EmptyPlanHero busy onCreate={onCreate} />);
    const cta = screen.getByRole('button', { name: '내 식단 만들기' });
    expect(cta).toBeDisabled();
    fireEvent.click(cta);
    expect(onCreate).not.toHaveBeenCalled();
  });
});
