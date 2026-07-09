'use client';

import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';

interface AutoOrderPromptProps {
  open: boolean;
  onStart: () => void;
  onLater: () => void;
}

/** 자동주문 제안 알림 1회 (FR-106) — "자동주문을 시작해볼까요?" */
export function AutoOrderPrompt({ open, onStart, onLater }: AutoOrderPromptProps) {
  const t = useTranslations('guestHome.autoOrderPrompt');

  return (
    <BottomSheet open={open} onClose={onLater} labelledBy="auto-order-prompt-title">
      <h2 id="auto-order-prompt-title" className="mb-2 text-base font-bold text-gray-900">
        {t('title')}
      </h2>
      <p className="mb-4 text-sm text-gray-600">{t('description')}</p>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onLater}
          className="flex-1 rounded-xl border border-gray-300 px-4 py-3 text-sm font-medium text-gray-700"
        >
          {t('later')}
        </button>
        <button
          type="button"
          onClick={onStart}
          className="flex-1 rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
        >
          {t('start')}
        </button>
      </div>
    </BottomSheet>
  );
}
