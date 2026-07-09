import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import { FRIDGE_EXPIRY_SOON_DAYS, type FridgeItem } from '@/features/home/types';

interface FridgePreviewCardProps {
  items: FridgeItem[];
}

/** 가상 냉장고 위젯 — 임박 배너 포함 (FR-101, 임박 재료 우선 정렬) */
export function FridgePreviewCard({ items }: FridgePreviewCardProps) {
  const t = useTranslations('guestHome.fridge');
  const sorted = [...items].sort((a, b) => a.expiresInDays - b.expiresInDays);
  const hasExpiringSoon = sorted.some((i) => i.expiresInDays <= FRIDGE_EXPIRY_SOON_DAYS);

  return (
    <section aria-label={t('title')} className="rounded-2xl border border-gray-200 bg-white p-5">
      <h2 className="mb-3 text-base font-bold text-gray-900">{t('title')}</h2>
      {hasExpiringSoon ? (
        <p role="status" className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {t('expiryBanner')}
        </p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {sorted.map((item) => (
          <li key={item.name} className="flex items-center justify-between text-sm">
            <span className="text-gray-900">
              {item.name}
              <span className="ml-2 text-xs text-gray-400">{item.quantity}</span>
            </span>
            <Badge tone={item.expiresInDays <= FRIDGE_EXPIRY_SOON_DAYS ? 'warning' : 'neutral'}>
              {t('expiresIn', { days: item.expiresInDays })}
            </Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}
