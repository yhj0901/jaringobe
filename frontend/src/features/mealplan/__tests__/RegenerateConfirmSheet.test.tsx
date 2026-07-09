import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { RegenerateConfirmSheet } from '@/features/mealplan/RegenerateConfirmSheet';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('RegenerateConfirmSheet (FR-209 확인 다이얼로그)', () => {
  it('open=false 면 렌더하지 않는다', () => {
    renderWithIntl(<RegenerateConfirmSheet open={false} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('확인/취소 콜백을 호출한다', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    renderWithIntl(<RegenerateConfirmSheet open onConfirm={onConfirm} onCancel={onCancel} />);

    expect(screen.getByText('식단을 전체 다시 만들까요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '다시 만들기' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
