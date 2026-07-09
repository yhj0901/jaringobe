'use client';

import { useTranslations } from 'next-intl';

interface PersistentCtaBannerProps {
  onClick: () => void;
}

/** 프롬프트 "아니오" 이후 상단 상시 CTA 배너 (FR-103) — 네이비 바 + 블루 액션 */
export function PersistentCtaBanner({ onClick }: PersistentCtaBannerProps) {
  const t = useTranslations('guestHome.cta');

  return (
    <div className="sticky top-0 z-40 bg-navy-800 px-4 py-2.5">
      <button
        type="button"
        onClick={onClick}
        className="mx-auto flex w-full max-w-[480px] items-center justify-between text-left text-[13px] font-bold text-white"
      >
        {t('banner')}
        <span aria-hidden className="text-brand-400">
          ›
        </span>
      </button>
    </div>
  );
}
