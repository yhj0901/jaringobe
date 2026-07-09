import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Stepper } from '@/shared/ui/Stepper';

function renderStepper(value: number, onChange = vi.fn()) {
  render(
    <Stepper
      value={value}
      min={1}
      max={10}
      onChange={onChange}
      label="가구 인원"
      decrementLabel="줄이기"
      incrementLabel="늘리기"
    />,
  );
  return onChange;
}

describe('Stepper', () => {
  it('증가/감소 버튼이 onChange 를 호출한다', () => {
    const onChange = renderStepper(3);
    fireEvent.click(screen.getByLabelText('늘리기'));
    expect(onChange).toHaveBeenCalledWith(4);
    fireEvent.click(screen.getByLabelText('줄이기'));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('최소값에서 감소 버튼이 비활성화된다', () => {
    renderStepper(1);
    expect(screen.getByLabelText('줄이기')).toBeDisabled();
    expect(screen.getByLabelText('늘리기')).toBeEnabled();
  });

  it('최대값에서 증가 버튼이 비활성화된다', () => {
    renderStepper(10);
    expect(screen.getByLabelText('늘리기')).toBeDisabled();
  });

  it('현재 값을 라이브 영역으로 노출한다', () => {
    renderStepper(5);
    expect(screen.getByRole('group', { name: '가구 인원' })).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});
