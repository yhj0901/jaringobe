import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import type { HomeViewModel } from '@/features/home/types';

interface AutoOrderCardProps {
  autoOrder: HomeViewModel['autoOrder'];
  /** 활성 상태에서 "시작하기" CTA — /login?next=/ 이동 (FR-106) */
  onStart?: () => void;
}

/** 자동주문 카드 — 비활성/활성 상태 (FR-101/106) */
export function AutoOrderCard({ autoOrder, onStart }: AutoOrderCardProps) {
  const t = useTranslations('guestHome.autoOrder');

  return (
    <section
      aria-label={t('title')}
      className={`rounded-2xl border p-5 ${autoOrder.active ? 'border-brand-500 bg-brand-50' : 'border-gray-200 bg-gray-50'}`}
    >
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-base font-bold text-gray-900">{t('title')}</h2>
        <Badge tone={autoOrder.active ? 'brand' : 'neutral'}>
          {autoOrder.active ? t('statusActive') : t('statusInactive')}
        </Badge>
      </div>
      <p className="mb-3 text-sm text-gray-600">
        {autoOrder.active ? t('descriptionActive') : t('descriptionInactive')}
      </p>
      <ul aria-label={t('storesLabel')} className="mb-3 flex flex-wrap gap-2">
        {autoOrder.stores.map((store) => (
          <li key={store.id}>
            <Badge tone="neutral">{store.name}</Badge>
          </li>
        ))}
      </ul>
      {autoOrder.active && autoOrder.recommendedItems !== undefined ? (
        <div className="mb-3">
          <h3 className="mb-1 text-xs font-medium text-gray-500">{t('recommendedLabel')}</h3>
          <ul className="flex flex-wrap gap-2">
            {autoOrder.recommendedItems.map((item) => (
              <li key={item} className="rounded-lg bg-white px-2 py-1 text-xs text-gray-700">
                {item}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {autoOrder.active ? (
        <button
          type="button"
          onClick={onStart}
          className="w-full rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
        >
          {t('startCta')}
        </button>
      ) : null}
    </section>
  );
}
