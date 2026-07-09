'use client';

import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';

interface EngagementPromptProps {
  open: boolean;
  onAccept: () => void;
  onDecline: () => void;
}

/** "예산안을 작성해 보시겠어요?" 바텀시트 (FR-102/103) */
export function EngagementPrompt({ open, onAccept, onDecline }: EngagementPromptProps) {
  const t = useTranslations('guestHome.prompt');

  return (
    <BottomSheet open={open} onClose={onDecline} labelledBy="engagement-prompt-title">
      <h2 id="engagement-prompt-title" className="mb-4 text-base font-bold text-gray-900">
        {t('title')}
      </h2>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onDecline}
          className="flex-1 rounded-xl border border-gray-300 px-4 py-3 text-sm font-medium text-gray-700"
        >
          {t('decline')}
        </button>
        <button
          type="button"
          onClick={onAccept}
          className="flex-1 rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
        >
          {t('accept')}
        </button>
      </div>
    </BottomSheet>
  );
}
