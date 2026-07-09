import { useTranslations } from 'next-intl';
import type { HomeViewModel } from '@/features/home/types';

interface AutoOrderCardProps {
  autoOrder: HomeViewModel['autoOrder'];
  /** 활성 상태에서 "시작하기" CTA — /login?next=/ 이동 (FR-106) */
  onStart?: () => void;
}

/**
 * 자동주문 카드 — 비활성/활성 상태 (FR-101/106).
 * 활성 시 디자인의 그린 그라디언트 자동주문 카드 재현, 비활성 시 뉴트럴 화이트 카드.
 */
export function AutoOrderCard({ autoOrder, onStart }: AutoOrderCardProps) {
  const t = useTranslations('guestHome.autoOrder');
  const { active } = autoOrder;

  return (
    <section
      aria-label={t('title')}
      className={
        active
          ? 'rounded-[20px] bg-[linear-gradient(150deg,#0F8A63,#0A6E4E)] p-4 text-white shadow-mint'
          : 'rounded-[20px] bg-white p-4 shadow-card'
      }
    >
      <div className="mb-2.5 flex items-center gap-2.5">
        <span
          aria-hidden
          className={`flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] ${
            active ? 'bg-white/15' : 'bg-mint-50'
          }`}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
            <path
              d="M5 8h14l-1 11a2 2 0 0 1-2 1.8H8a2 2 0 0 1-2-1.8L5 8z"
              stroke={active ? '#fff' : '#0FB07A'}
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <path
              d="M9 8V6a3 3 0 0 1 6 0v2"
              stroke={active ? '#fff' : '#0FB07A'}
              strokeWidth="1.8"
              strokeLinecap="round"
            />
            <path
              d="M10.5 13.5l1.5 1.5 3-3"
              stroke="#36E0A6"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <h2
          className={`flex-1 text-[14.5px] font-extrabold ${active ? 'text-white' : 'text-navy-900'}`}
        >
          {t('title')}
        </h2>
        <span
          className={`rounded-full px-2.5 py-1 text-[10.5px] font-extrabold ${
            active ? 'bg-white/15 text-mint-300' : 'bg-[#F0F2F6] text-ink-400'
          }`}
        >
          {active ? t('statusActive') : t('statusInactive')}
        </span>
      </div>

      <p className={`mb-3 text-[12.5px] leading-relaxed ${active ? 'text-white/80' : 'text-ink-500'}`}>
        {active ? t('descriptionActive') : t('descriptionInactive')}
      </p>

      <ul aria-label={t('storesLabel')} className="mb-1 flex flex-wrap gap-1.5">
        {autoOrder.stores.map((store) => (
          <li
            key={store.id}
            className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${
              active ? 'bg-white/15 text-white' : 'bg-[#F0F2F6] text-ink-500'
            }`}
          >
            {store.name}
          </li>
        ))}
      </ul>

      {active && autoOrder.recommendedItems !== undefined ? (
        <div className="mt-3 rounded-[13px] bg-white/10 px-3.5 py-3">
          <h3 className="mb-1.5 text-xs font-bold text-white/80">{t('recommendedLabel')}</h3>
          <ul className="flex flex-wrap gap-1.5">
            {autoOrder.recommendedItems.map((item) => (
              <li
                key={item}
                className="rounded-lg bg-white/15 px-2 py-1 text-xs font-semibold text-white"
              >
                {item}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {active ? (
        <button
          type="button"
          onClick={onStart}
          className="mt-3 w-full rounded-[14px] bg-white px-4 py-3 text-sm font-extrabold text-mint-700"
        >
          {t('startCta')}
        </button>
      ) : null}
    </section>
  );
}
