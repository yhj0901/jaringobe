import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { BottomSheet } from '@/shared/ui/BottomSheet';

describe('BottomSheet', () => {
  it('open=false 이면 렌더하지 않는다', () => {
    render(
      <BottomSheet open={false} onClose={() => undefined} labelledBy="t">
        <p>내용</p>
      </BottomSheet>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('열리면 dialog 역할로 렌더하고 시트로 포커스를 이동한다', () => {
    render(
      <BottomSheet open onClose={() => undefined} labelledBy="t">
        <p id="t">내용</p>
      </BottomSheet>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-labelledby', 't');
    expect(dialog).toHaveFocus();
  });

  it('ESC 키로 닫힌다', () => {
    const onClose = vi.fn();
    render(
      <BottomSheet open onClose={onClose} labelledBy="t">
        <p id="t">내용</p>
      </BottomSheet>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('바깥 클릭으로 닫히고 내부 클릭은 무시한다', () => {
    const onClose = vi.fn();
    render(
      <div>
        <button type="button">outside</button>
        <BottomSheet open onClose={onClose} labelledBy="t">
          <p id="t">내용</p>
        </BottomSheet>
      </div>,
    );
    fireEvent.mouseDown(screen.getByText('내용'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.mouseDown(screen.getByText('outside'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('닫히면 이전 포커스를 복원한다', () => {
    const { rerender } = render(
      <div>
        <button type="button">trigger</button>
      </div>,
    );
    screen.getByText('trigger').focus();
    rerender(
      <div>
        <button type="button">trigger</button>
        <BottomSheet open onClose={() => undefined} labelledBy="t">
          <p id="t">내용</p>
        </BottomSheet>
      </div>,
    );
    expect(screen.getByRole('dialog')).toHaveFocus();
    rerender(
      <div>
        <button type="button">trigger</button>
        <BottomSheet open={false} onClose={() => undefined} labelledBy="t">
          <p id="t">내용</p>
        </BottomSheet>
      </div>,
    );
    expect(screen.getByText('trigger')).toHaveFocus();
  });
});
