import { fireEvent, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DeliveryConfirmSheet } from '@/features/fridge/DeliveryConfirmSheet';
import { renderWithIntl } from '@/test/renderWithIntl';

it('배송 확인 3개 액션을 i18n 라벨로 제공한다', () => {
  const onYes = vi.fn();
  const onAdjust = vi.fn();
  const onNotYet = vi.fn();
  renderWithIntl(
    <DeliveryConfirmSheet busy={false} onYes={onYes} onAdjust={onAdjust} onNotYet={onNotYet} />,
  );
  expect(screen.getByText(/이 재료들을 냉장고에 담아둘게요/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '맞아요' }));
  fireEvent.click(screen.getByRole('button', { name: '수량 수정' }));
  fireEvent.click(screen.getByRole('button', { name: '아직 안 왔어요' }));
  expect(onYes).toHaveBeenCalledTimes(1);
  expect(onAdjust).toHaveBeenCalledTimes(1);
  expect(onNotYet).toHaveBeenCalledTimes(1);
});
