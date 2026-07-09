import { useTranslations } from 'next-intl';
import { MealCard } from '@/features/home/MealCard';
import type { DayPlan } from '@/features/home/types';

interface MealPlanSectionProps {
  weekPlan: DayPlan[];
  onRecipeClick?: () => void;
}

/**
 * 주간 식단 섹션 — 오늘(첫째 날) 아침/점심/저녁 3행 리스트 카드 + 주간 스트립 (FR-101).
 * 디자인의 "오늘의 식단" 화이트 카드(슬롯 도트 + 행 리스트) 재현.
 */
export function MealPlanSection({ weekPlan, onRecipeClick }: MealPlanSectionProps) {
  const t = useTranslations('guestHome.mealPlan');
  const today = weekPlan[0];

  return (
    <section aria-label={t('title')} className="mt-1.5 flex flex-col gap-2.5">
      <h2 className="px-0.5 text-base font-extrabold text-navy-900">{t('title')}</h2>
      <div className="rounded-[20px] bg-white px-4 py-1 shadow-card">
        {today?.meals.map((meal) => (
          <MealCard key={meal.slot} meal={meal} onRecipeClick={onRecipeClick} />
        ))}
      </div>
      <ol aria-label={t('weekStrip')} className="flex gap-1.5 overflow-x-auto px-0.5 text-xs">
        {weekPlan.map((day, index) => (
          <li
            key={day.day}
            className={`shrink-0 rounded-full px-2.5 py-1 font-semibold ${
              index === 0 ? 'bg-brand-600 font-bold text-white' : 'bg-white text-ink-400 shadow-sm'
            }`}
          >
            {t(`day.${day.day}`)}
          </li>
        ))}
      </ol>
    </section>
  );
}
