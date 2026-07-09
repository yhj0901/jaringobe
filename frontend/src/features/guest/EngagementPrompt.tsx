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
      <h2 id="engagement-prompt-title" className="mb-4 text-base font-extrabold text-navy-900">
        {t('title')}
      </h2>
      <div className="flex gap-2.5">
        <button
          type="button"
          onClick={onDecline}
          className="flex-1 rounded-[14px] bg-[#F0F2F6] px-4 py-3.5 text-sm font-bold text-ink-500"
        >
          {t('decline')}
        </button>
        <button
          type="button"
          onClick={onAccept}
          className="flex-1 rounded-[14px] bg-brand-600 px-4 py-3.5 text-sm font-extrabold text-white shadow-cta"
        >
          {t('accept')}
        </button>
      </div>
    </BottomSheet>
  );
}
