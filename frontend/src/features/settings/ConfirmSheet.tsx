'use client';

import { useId } from 'react';
import { BottomSheet } from '@/shared/ui/BottomSheet';

interface ConfirmSheetProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  /** 파괴적 동작(로그아웃·연동 해제) — 확인 버튼을 경고 색으로 */
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 설정 공통 확인 시트 (ui-design 9장) — 로그아웃/스토어 연동·해제/식단 재생성 확인에 재사용.
 */
export function ConfirmSheet({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmSheetProps) {
  const titleId = useId();

  return (
    <BottomSheet open={open} onClose={onCancel} labelledBy={titleId}>
      <h2 id={titleId} className="text-lg font-extrabold tracking-tight text-navy-900">
        {title}
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-500">{description}</p>
      <div className="mt-5 flex gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={onCancel}
          className="flex-1 rounded-2xl bg-[#F0F2F6] px-4 py-3.5 text-sm font-bold text-ink-500 disabled:opacity-60"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onConfirm}
          className={`flex-1 rounded-2xl px-4 py-3.5 text-sm font-extrabold text-white disabled:opacity-60 ${
            destructive ? 'bg-[#C2453A]' : 'bg-brand-600 shadow-cta'
          }`}
        >
          {confirmLabel}
        </button>
      </div>
    </BottomSheet>
  );
}
