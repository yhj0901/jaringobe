'use client';

import { useTranslations } from 'next-intl';

interface PersistentCtaBannerProps {
  onClick: () => void;
}

/** 프롬프트 "아니오" 이후 상단 상시 CTA 배너 (FR-103) */
export function PersistentCtaBanner({ onClick }: PersistentCtaBannerProps) {
  const t = useTranslations('guestHome.cta');

  return (
    <div className="sticky top-0 z-40 border-b border-brand-100 bg-brand-50 px-4 py-2">
      <button
        type="button"
        onClick={onClick}
        className="mx-auto block w-full max-w-3xl text-left text-sm font-medium text-brand-700 underline underline-offset-2"
      >
        {t('banner')}
      </button>
    </div>
  );
}
