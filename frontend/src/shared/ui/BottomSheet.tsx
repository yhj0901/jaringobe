'use client';

import { useEffect, useRef, type ReactNode } from 'react';

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  children: ReactNode;
}

/**
 * 비모달 바텀시트 (ui-design 4장 접근성 규칙)
 * - role="dialog", 열림 직후 시트 내부로 포커스 이동 (트랩은 걸지 않음 — 스크린리더 탐색 강탈 금지)
 * - ESC / 바깥 클릭으로 닫기, 닫힐 때 이전 포커스 복원
 */
export function BottomSheet({ open, onClose, labelledBy, children }: BottomSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    sheetRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    const handlePointerDown = (event: MouseEvent) => {
      if (sheetRef.current && !sheetRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handlePointerDown);
      previousFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={sheetRef}
      role="dialog"
      aria-labelledby={labelledBy}
      tabIndex={-1}
      className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-[480px] rounded-t-[26px] bg-white px-5 pb-7 pt-2.5 shadow-sheet outline-none"
    >
      <div aria-hidden className="mx-auto mb-4 h-[5px] w-10 rounded-full bg-[#E1E6EF]" />
      {children}
    </div>
  );
}
