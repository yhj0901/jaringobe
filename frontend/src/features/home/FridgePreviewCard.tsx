import { useTranslations } from 'next-intl';
import { FRIDGE_EXPIRY_SOON_DAYS, type FridgeItem } from '@/features/home/types';

interface FridgePreviewCardProps {
  items: FridgeItem[];
}

/**
 * 가상 냉장고 위젯 — 임박 배너 포함 (FR-101, 임박 재료 우선 정렬).
 * 디자인의 "곧 상하는 재료" 카드(오렌지 보더 + 경고 아이콘 + 임박 일수) 재현.
 */
export function FridgePreviewCard({ items }: FridgePreviewCardProps) {
  const t = useTranslations('guestHome.fridge');
  const sorted = [...items].sort((a, b) => a.expiresInDays - b.expiresInDays);
  const hasExpiringSoon = sorted.some((i) => i.expiresInDays <= FRIDGE_EXPIRY_SOON_DAYS);

  return (
    <section
      aria-label={t('title')}
      className="rounded-[20px] border border-flame-200 bg-white p-4 shadow-card"
    >
      <div className="mb-2.5 flex items-center gap-2.5">
        <span
          aria-hidden
          className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-flame-50"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 3l9.5 16.5H2.5L12 3z"
              stroke="#E0651A"
              strokeWidth="2"
              strokeLinejoin="round"
            />
            <path d="M12 10v4" stroke="#E0651A" strokeWidth="2" strokeLinecap="round" />
            <circle cx="12" cy="17" r="1.1" fill="#E0651A" />
          </svg>
        </span>
        <h2 className="flex-1 text-[14.5px] font-extrabold text-navy-900">{t('title')}</h2>
      </div>
      <ul className="flex flex-col">
        {sorted.map((item) => (
          <li key={item.name} className="flex items-center justify-between py-1.5">
            <span className="text-[13.5px] font-semibold text-ink-800">
              {item.name}
              <span className="ml-1.5 text-xs font-medium text-ink-300">{item.quantity}</span>
            </span>
            <span
              className={`text-xs font-extrabold tabular-nums ${
                item.expiresInDays <= FRIDGE_EXPIRY_SOON_DAYS ? 'text-flame-500' : 'text-ink-300'
              }`}
            >
              {t('expiresIn', { days: item.expiresInDays })}
            </span>
          </li>
        ))}
      </ul>
      {hasExpiringSoon ? (
        <p
          role="status"
          className="mt-2 rounded-[9px] bg-flame-50 px-2.5 py-2 text-[11.5px] font-semibold text-flame-600"
        >
          {t('expiryBanner')}
        </p>
      ) : null}
    </section>
  );
}
