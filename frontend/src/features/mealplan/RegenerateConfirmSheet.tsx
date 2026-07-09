'use client';

import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';

interface RegenerateConfirmSheetProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * 전체 재생성 확인 다이얼로그 (FR-209) — rate limit 준수를 위해 확인 후에만 요청.
 */
export function RegenerateConfirmSheet({ open, onConfirm, onCancel }: RegenerateConfirmSheetProps) {
  const t = useTranslations('memberHome.regenerateConfirm');

  return (
    <BottomSheet open={open} onClose={onCancel} labelledBy="regenerate-confirm-title">
      <h2
        id="regenerate-confirm-title"
        className="text-lg font-extrabold tracking-tight text-navy-900"
      >
        {t('title')}
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-500">{t('description')}</p>
      <div className="mt-5 flex gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 rounded-2xl bg-[#F0F2F6] px-4 py-3.5 text-sm font-bold text-ink-500"
        >
          {t('cancel')}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          className="flex-1 rounded-2xl bg-brand-600 px-4 py-3.5 text-sm font-extrabold text-white shadow-cta"
        >
          {t('confirm')}
        </button>
      </div>
    </BottomSheet>
  );
}
