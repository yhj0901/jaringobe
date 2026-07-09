import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PlanCreateSheet } from '@/features/mealplan/PlanCreateSheet';
import { IntlWrapper, renderWithIntl } from '@/test/renderWithIntl';

function addChip(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: 'Enter' });
}

describe('PlanCreateSheet (FR-203)', () => {
  it('open=false 면 렌더하지 않는다', () => {
    renderWithIntl(
      <PlanCreateSheet open={false} onClose={vi.fn()} onSubmit={vi.fn()} />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('기본 기간 7일 + 스테퍼로 조정해 제출한다', () => {
    const onSubmit = vi.fn();
    renderWithIntl(<PlanCreateSheet open onClose={vi.fn()} onSubmit={onSubmit} />);

    expect(screen.getByText('7일')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '기간 줄이기' }));
    fireEvent.click(screen.getByRole('button', { name: '식단 생성하기' }));

    expect(onSubmit).toHaveBeenCalledWith({ days: 6, allergies: [], preferences: [] });
  });

  it('알레르기/선호 칩을 추가·삭제하고 제출값에 반영한다', () => {
    const onSubmit = vi.fn();
    renderWithIntl(<PlanCreateSheet open onClose={vi.fn()} onSubmit={onSubmit} />);

    const allergyInput = screen.getByLabelText('알레르기 (선택)');
    addChip(allergyInput, '땅콩');
    addChip(allergyInput, '우유');
    expect(screen.getByRole('button', { name: '땅콩 삭제' })).toBeInTheDocument();

    const preferenceInput = screen.getByLabelText('선호 (선택)');
    fireEvent.change(preferenceInput, { target: { value: '한식' } });
    fireEvent.click(screen.getAllByRole('button', { name: '추가' })[1] as HTMLElement);

    fireEvent.click(screen.getByRole('button', { name: '우유 삭제' }));
    fireEvent.click(screen.getByRole('button', { name: '식단 생성하기' }));

    expect(onSubmit).toHaveBeenCalledWith({
      days: 7,
      allergies: ['땅콩'],
      preferences: ['한식'],
    });
  });

  it('30자 초과 항목은 에러를 표시하고 추가하지 않는다 (CWE-79 길이 제한)', () => {
    renderWithIntl(<PlanCreateSheet open onClose={vi.fn()} onSubmit={vi.fn()} />);

    const input = screen.getByLabelText('알레르기 (선택)');
    addChip(input, 'a'.repeat(31));

    expect(screen.getByRole('alert')).toHaveTextContent('항목은 30자 이내로 입력해 주세요.');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByRole('button', { name: /삭제$/ })).not.toBeInTheDocument();
  });

  it('중복·최대 10개 초과 항목은 에러를 표시한다', () => {
    renderWithIntl(<PlanCreateSheet open onClose={vi.fn()} onSubmit={vi.fn()} />);

    const input = screen.getByLabelText('선호 (선택)');
    addChip(input, '항목0');
    addChip(input, '항목0');
    expect(screen.getByRole('alert')).toHaveTextContent('이미 추가한 항목이에요.');

    // 입력 수정 시 에러 해제 → 10개 채운 뒤 초과 에러 검증
    fireEvent.change(input, { target: { value: '항목1' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    for (let i = 1; i < 10; i += 1) addChip(input, `항목${i}`);
    addChip(input, '항목10');
    expect(screen.getByRole('alert')).toHaveTextContent('최대 10개까지 추가할 수 있어요.');
  });

  it('빈 입력은 조용히 무시한다 (에러 미표시)', () => {
    renderWithIntl(<PlanCreateSheet open onClose={vi.fn()} onSubmit={vi.fn()} />);
    const input = screen.getByLabelText('알레르기 (선택)');
    addChip(input, '   ');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('busy=true 면 제출 버튼이 비활성화된다 (연타 방지, FR-204)', () => {
    const onSubmit = vi.fn();
    renderWithIntl(<PlanCreateSheet open busy onClose={vi.fn()} onSubmit={onSubmit} />);
    const submit = screen.getByRole('button', { name: '식단 생성하기' });
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('다시 열면 입력이 초기화된다', () => {
    const { rerender } = render(<PlanCreateSheet open onClose={vi.fn()} onSubmit={vi.fn()} />, {
      wrapper: IntlWrapper,
    });
    addChip(screen.getByLabelText('알레르기 (선택)'), '땅콩');
    fireEvent.click(screen.getByRole('button', { name: '기간 늘리기' }));

    rerender(<PlanCreateSheet open={false} onClose={vi.fn()} onSubmit={vi.fn()} />);
    rerender(<PlanCreateSheet open onClose={vi.fn()} onSubmit={vi.fn()} />);

    expect(screen.getByText('7일')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '땅콩 삭제' })).not.toBeInTheDocument();
  });
});
