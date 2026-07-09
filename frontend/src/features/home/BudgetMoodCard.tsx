import { useLocale, useTranslations } from 'next-intl';
import { MoneyText } from '@/shared/ui/MoneyText';
import type { HomeViewModel } from '@/features/home/types';

interface BudgetMoodCardProps {
  budgetMood: HomeViewModel['budgetMood'];
}

/** 예산 무드 — 남은 예산·절약·폐기 절감 (FR-101, Money 표시) */
export function BudgetMoodCard({ budgetMood }: BudgetMoodCardProps) {
  const t = useTranslations('guestHome.budgetMood');
  const locale = useLocale();

  const rows = [
    { key: 'remaining', money: budgetMood.remaining },
    { key: 'saved', money: budgetMood.saved },
    { key: 'wastePrevented', money: budgetMood.wastePrevented },
  ] as const;

  return (
    <section
      aria-label={t('title')}
      className="rounded-2xl bg-brand-600 p-5 text-white"
    >
      <h2 className="mb-3 text-sm font-medium opacity-90">{t('title')}</h2>
      <dl className="grid grid-cols-3 gap-3">
        {rows.map(({ key, money }) => (
          <div key={key}>
            <dt className="text-xs opacity-80">{t(key)}</dt>
            <dd className="mt-1 text-sm font-bold">
              <MoneyText money={money} locale={locale} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
