import { useTranslations } from 'next-intl';
import { MealCard } from '@/features/home/MealCard';
import type { DayPlan } from '@/features/home/types';

interface MealPlanSectionProps {
  weekPlan: DayPlan[];
  onRecipeClick?: () => void;
}

/** 주간 식단 섹션 — 오늘(첫째 날) 아침/점심/저녁 3카드 + 주간 스트립 (FR-101) */
export function MealPlanSection({ weekPlan, onRecipeClick }: MealPlanSectionProps) {
  const t = useTranslations('guestHome.mealPlan');
  const today = weekPlan[0];

  return (
    <section aria-label={t('title')} className="flex flex-col gap-3">
      <h2 className="text-base font-bold text-gray-900">{t('title')}</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        {today?.meals.map((meal) => (
          <MealCard key={meal.slot} meal={meal} onRecipeClick={onRecipeClick} />
        ))}
      </div>
      <ol aria-label={t('weekStrip')} className="flex gap-2 overflow-x-auto text-xs text-gray-500">
        {weekPlan.map((day, index) => (
          <li
            key={day.day}
            className={`shrink-0 rounded-lg px-2 py-1 ${index === 0 ? 'bg-brand-100 font-bold text-brand-700' : 'bg-gray-50'}`}
          >
            {t(`day.${day.day}`)}
          </li>
        ))}
      </ol>
    </section>
  );
}
