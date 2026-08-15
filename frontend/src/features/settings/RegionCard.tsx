'use client';

import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import type { Country } from '@/shared/api/types';

interface RegionCardProps {
  /** 현재 지역 — user.country (KR/US 외 값은 KR 로 간주) */
  country: string;
  busy: boolean;
  /** 다른 지역 선택 시 호출 — 확인 시트는 호출측(SettingsController) */
  onSwitch: (target: Country) => void;
}

const OPTIONS: { value: Country; labelKey: 'korea' | 'global' }[] = [
  { value: 'KR', labelKey: 'korea' },
  { value: 'US', labelKey: 'global' },
];

/**
 * 지역·통화 설정 (FR-601/605, ui-design 12장)
 * 한국 ₩ / 글로벌 $ 세그먼트 토글. country != KR 시 "글로벌" 배지. 전환 확인·PUT 은 호출측.
 */
export function RegionCard({ country, busy, onSwitch }: RegionCardProps) {
  const t = useTranslations('settings.region');
  const current: Country = country === 'US' ? 'US' : 'KR';

  return (
    <section aria-label={t('section')} className="mt-[22px]">
      <div className="mx-0.5 mb-2 flex items-center gap-2">
        <h2 className="text-xs font-extrabold tracking-wide text-ink-400">{t('section')}</h2>
        {current !== 'KR' ? <Badge tone="neutral">{t('globalBadge')}</Badge> : null}
      </div>
      <div
        role="group"
        aria-label={t('section')}
        className="flex gap-2 rounded-[18px] bg-white p-2 shadow-card"
      >
        {OPTIONS.map((option) => {
          const active = option.value === current;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              disabled={busy || active}
              onClick={() => onSwitch(option.value)}
              className={`flex-1 rounded-[13px] py-3 text-sm font-extrabold transition disabled:opacity-70 ${
                active ? 'bg-brand-600 text-white shadow-cta' : 'bg-surface-app text-ink-500'
              }`}
            >
              {t(option.labelKey)}
            </button>
          );
        })}
      </div>
      <p className="mx-0.5 mt-2 text-xs leading-relaxed text-ink-300">{t('noRetroNotice')}</p>
    </section>
  );
}
