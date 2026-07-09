import { useLocale, useTranslations } from 'next-intl';
import { MoneyText } from '@/shared/ui/MoneyText';
import type { Money } from '@/shared/api/types';

interface EmptyPlanHeroProps {
  /** 온보딩 직후 알게 된 내 예산 (없으면 금액 없이 일반 카피) */
  budget?: Money | null;
  /** "내 식단 만들기" CTA — 생성 시트 열기 (FR-202) */
  onCreate: () => void;
  /** 생성 진행 중 연타 방지 (FR-204) */
  busy?: boolean;
}

/**
 * 빈 상태 예산 락 히어로 (FR-202) — 빈 상태 자체가 전환 장치.
 * 예산 락 히어로 톤(네이비 그라디언트 + 민트 자물쇠) + "내 식단 만들기" 대형 CTA.
 */
export function EmptyPlanHero({ budget, onCreate, busy = false }: EmptyPlanHeroProps) {
  const t = useTranslations('memberHome.empty');
  const locale = useLocale();

  return (
    <section
      aria-label={t('title')}
      className="rounded-3xl bg-[linear-gradient(150deg,#1C2E58_0%,#0B1B3A_100%)] p-6 text-white shadow-hero"
    >
      <span className="flex items-center gap-1.5 text-[13px] font-bold text-white/85">
        <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none">
          <rect x="4" y="10" width="16" height="11" rx="2.5" stroke="#36E0A6" strokeWidth="2" />
          <path
            d="M8 10V7a4 4 0 0 1 8 0v3"
            stroke="#36E0A6"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        {t('lockLabel')}
      </span>

      <h2 className="mt-4 text-[23px] font-extrabold leading-snug tracking-tight">{t('title')}</h2>
      <p className="mt-2 text-[13px] leading-relaxed text-white/70">{t('description')}</p>

      {budget ? (
        <div className="mt-5">
          <div className="text-[12px] font-semibold text-white/60">{t('budgetLabel')}</div>
          <div className="mt-0.5 text-[30px] font-extrabold leading-none tracking-tight tabular-nums">
            <MoneyText money={budget} locale={locale} />
          </div>
        </div>
      ) : null}

      <button
        type="button"
        onClick={onCreate}
        disabled={busy}
        className="mt-6 w-full rounded-[16px] bg-mint-500 px-4 py-4 text-[15px] font-extrabold text-navy-900 shadow-cta disabled:opacity-60"
      >
        {t('cta')}
      </button>
    </section>
  );
}
