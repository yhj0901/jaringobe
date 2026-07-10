import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import { Link } from '@/i18n/routing';

export type LockedFeature = 'fridge' | 'order';

/** 잠금 카드 아이콘 — HomeShell 탭바 글리프 톤 재사용 */
function FeatureIcon({ feature }: { feature: LockedFeature }) {
  const stroke = '#9AA6BD';
  if (feature === 'fridge') {
    return (
      <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
        <rect x="6" y="3" width="12" height="18" rx="2.5" stroke={stroke} strokeWidth="1.9" />
        <path d="M6 10h12" stroke={stroke} strokeWidth="1.9" />
        <path d="M9 6.5v1.5M9 12.5V14" stroke={stroke} strokeWidth="1.9" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
      <circle cx="9" cy="20" r="1.5" stroke={stroke} strokeWidth="1.6" />
      <circle cx="18" cy="20" r="1.5" stroke={stroke} strokeWidth="1.6" />
      <path
        d="M2.5 4h2L7 15.2a1.5 1.5 0 0 0 1.5 1.2h8.5a1.5 1.5 0 0 0 1.5-1.2L20.5 7H6"
        stroke={stroke}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * 회원 홈 기능 카드 (FR-208) — 냉장고/자동주문을 게스트 샘플 대신 표시.
 * `href` 가 있으면 해당 페이지로 이동하는 활성 카드(예: 가상 냉장고 → /fridge),
 * 없으면 "준비 중" 잠금 카드.
 */
export function LockedFeatureCard({ feature, href }: { feature: LockedFeature; href?: string }) {
  const t = useTranslations('memberHome.locked');
  const active = href !== undefined;
  const title = t(`${feature}Title`);
  const description = active ? t('fridgeActiveDescription') : t(`${feature}Description`);

  const inner = (
    <>
      <div className="mb-1.5 flex items-center gap-2.5">
        <span
          aria-hidden
          className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] bg-[#F0F2F6]"
        >
          <FeatureIcon feature={feature} />
        </span>
        <h2
          className={`flex-1 text-[14.5px] font-extrabold ${active ? 'text-navy-900' : 'text-ink-400'}`}
        >
          {title}
        </h2>
        <Badge tone="neutral">{active ? t('open') : t('badge')}</Badge>
      </div>
      <p className="text-[12.5px] leading-relaxed text-ink-300">{description}</p>
    </>
  );

  if (active) {
    return (
      <Link
        href={href}
        aria-label={title}
        className="block rounded-[20px] bg-white p-4 shadow-card transition hover:shadow-cta"
      >
        {inner}
      </Link>
    );
  }
  return (
    <section aria-label={title} className="rounded-[20px] bg-white p-4 shadow-card">
      {inner}
    </section>
  );
}
