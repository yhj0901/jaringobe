import { useTranslations } from 'next-intl';
import type { HomeViewModel } from '@/features/home/types';

interface AutoOrderCardProps {
  autoOrder: HomeViewModel['autoOrder'];
  /** 활성 상태에서 "시작하기" CTA — /login?next=/ 이동 (FR-106) */
  onStart?: () => void;
  /**
   * 활성 CTA 라벨. 미지정 시 guestHome.autoOrder.startCta (게스트 불변).
   * 회원은 memberHome.autoOrder.viewCartCta 를 넘긴다.
   */
  ctaLabel?: string;
  /**
   * 비활성 CTA 라벨. 지정 시에만 비활성 카드에도 버튼을 그린다 (회원 "스토어 연동하기").
   * 게스트는 넘기지 않아 기존처럼 비활성 버튼 없음.
   */
  inactiveCtaLabel?: string;
  /** 설명 문구 덮어쓰기 — 미지정 시 guestHome.autoOrder descriptionActive/Inactive */
  description?: string;
  /** 추천 섹션 제목 덮어쓰기 — 미지정 시 guestHome.autoOrder.recommendedLabel */
  recommendedLabel?: string;
  /** 추천 칩 초과분 라벨 (예: "+2"). 있으면 칩 목록 끝에 표시 */
  moreCountLabel?: string;
  /** preview 로딩 중 aria-busy (회원 홈) */
  busy?: boolean;
}

/**
 * 자동주문 카드 — 비활성/활성 상태 (FR-101/106).
 * 활성 시 디자인의 그린 그라디언트 자동주문 카드 재현, 비활성 시 뉴트럴 화이트 카드.
 * 게스트 카피/동작은 기본 props 로 불변. 회원 CTA 는 optional 라벨로만 확장 (복제 금지).
 */
export function AutoOrderCard({
  autoOrder,
  onStart,
  ctaLabel,
  inactiveCtaLabel,
  description,
  recommendedLabel,
  moreCountLabel,
  busy = false,
}: AutoOrderCardProps) {
  const t = useTranslations('guestHome.autoOrder');
  const { active } = autoOrder;
  const activeCta = ctaLabel ?? t('startCta');
  const showCta = active || Boolean(inactiveCtaLabel);
  const ctaText = active ? activeCta : inactiveCtaLabel;
  const body = description ?? (active ? t('descriptionActive') : t('descriptionInactive'));

  return (
    <section
      aria-label={t('title')}
      aria-busy={busy || undefined}
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
        {body}
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
          <h3 className="mb-1.5 text-xs font-bold text-white/80">
            {recommendedLabel ?? t('recommendedLabel')}
          </h3>
          <ul className="flex flex-wrap gap-1.5">
            {autoOrder.recommendedItems.map((item) => (
              <li
                key={item}
                className="rounded-lg bg-white/15 px-2 py-1 text-xs font-semibold text-white"
              >
                {item}
              </li>
            ))}
            {moreCountLabel ? (
              <li className="rounded-lg bg-white/15 px-2 py-1 text-xs font-semibold text-white">
                {moreCountLabel}
              </li>
            ) : null}
          </ul>
        </div>
      ) : null}

      {showCta && ctaText ? (
        <button
          type="button"
          onClick={onStart}
          className={
            active
              ? 'mt-3 w-full rounded-[14px] bg-white px-4 py-3 text-sm font-extrabold text-mint-700'
              : 'mt-3 w-full rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta'
          }
        >
          {ctaText}
        </button>
      ) : null}
    </section>
  );
}
