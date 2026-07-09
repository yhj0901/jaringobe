import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { OverBudgetBanner } from '@/features/mealplan/OverBudgetBanner';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('OverBudgetBanner (FR-206)', () => {
  it('초과 안내를 role=alert 로 표시하고 재생성 CTA 를 호출한다', () => {
    const onRegenerate = vi.fn();
    renderWithIntl(<OverBudgetBanner onRegenerate={onRegenerate} />);

    expect(screen.getByRole('alert')).toHaveTextContent('식단이 예산을 초과했어요');
    fireEvent.click(screen.getByRole('button', { name: '예산에 맞게 다시 생성' }));
    expect(onRegenerate).toHaveBeenCalledTimes(1);
  });

  it('busy=true 면 재생성 버튼이 비활성화된다 (연타 방지)', () => {
    const onRegenerate = vi.fn();
    renderWithIntl(<OverBudgetBanner busy onRegenerate={onRegenerate} />);
    const button = screen.getByRole('button', { name: '예산에 맞게 다시 생성' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onRegenerate).not.toHaveBeenCalled();
  });

  it('en 로캘에서도 렌더된다 (i18n)', () => {
    renderWithIntl(<OverBudgetBanner onRegenerate={vi.fn()} />, 'en');
    expect(screen.getByRole('alert')).toHaveTextContent('This plan is over budget');
  });
});
