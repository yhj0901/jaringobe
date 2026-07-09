import { useLocale, useTranslations } from 'next-intl';
import { MoneyText } from '@/shared/ui/MoneyText';
import type { HomeViewModel } from '@/features/home/types';

interface BudgetMoodCardProps {
  budgetMood: HomeViewModel['budgetMood'];
  /** 게스트 샘플 데이터 여부 — 히어로 우측에 "예시" 칩 표시 */
  sample?: boolean;
}

/**
 * 예산 무드 — 남은 예산·절약·폐기 절감 (FR-101, Money 표시).
 * 디자인의 예산 락 히어로(네이비 그라디언트 + 자물쇠) + 절약 스트립(그린/블루 타일) 재현.
 */
export function BudgetMoodCard({ budgetMood, sample = false }: BudgetMoodCardProps) {
  const t = useTranslations('guestHome');
  const locale = useLocale();

  return (
    <section aria-label={t('budgetMood.title')} className="flex flex-col gap-3">
      {/* 예산 락 히어로 */}
      <div className="rounded-3xl bg-[linear-gradient(150deg,#1C2E58_0%,#0B1B3A_100%)] p-5 text-white shadow-hero">
        <div className="mb-3.5 flex items-center justify-between">
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
            {t('budgetMood.lockLabel')}
          </span>
          {sample ? (
            <span className="rounded-full bg-white/15 px-2.5 py-1 text-[11.5px] font-bold text-mint-300">
              {t('sampleLabel')}
            </span>
          ) : null}
        </div>
        <div className="text-[13px] font-semibold text-white/60">{t('budgetMood.remaining')}</div>
        <div className="mt-1 text-[38px] font-extrabold leading-none tracking-tight tabular-nums">
          <MoneyText money={budgetMood.remaining} locale={locale} />
        </div>
      </div>

      {/* 절약 스트립: 아낀 식비(그린) + 폐기 절감(블루) */}
      <dl className="flex gap-2.5">
        <div className="flex flex-1 items-center gap-2.5 rounded-2xl bg-mint-50 px-3.5 py-3">
          <span
            aria-hidden
            className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-mint-500"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2v20M17 6H9.5a3 3 0 0 0 0 6h5a3 3 0 0 1 0 6H6"
                stroke="#fff"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <dt className="text-[11.5px] font-semibold text-mint-600">{t('budgetMood.saved')}</dt>
            <dd className="text-base font-extrabold tabular-nums text-mint-700">
              <MoneyText money={budgetMood.saved} locale={locale} />
            </dd>
          </div>
        </div>
        <div className="flex flex-1 items-center gap-2.5 rounded-2xl bg-brand-50 px-3.5 py-3">
          <span
            aria-hidden
            className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-brand-600"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M7 10c0 6 5 9 5 9s5-3 5-9a5 5 0 0 0-10 0z"
                stroke="#fff"
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <path d="M12 19V6" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <dt className="text-[11.5px] font-semibold text-brand-700">
              {t('budgetMood.wastePrevented')}
            </dt>
            <dd className="text-base font-extrabold tabular-nums text-brand-700">
              <MoneyText money={budgetMood.wastePrevented} locale={locale} />
            </dd>
          </div>
        </div>
      </dl>
    </section>
  );
}
