import { useTranslations } from 'next-intl';
import { MealCard } from '@/features/home/MealCard';
import type { DayPlan } from '@/features/home/types';

/** meal 탭 스크롤 목적지 (FR-208) */
export const MEAL_SECTION_ID = 'home-meal-section';

interface MealPlanSectionProps {
  weekPlan: DayPlan[];
  onRecipeClick?: () => void;
  /** [member 옵셔널 확장] 선택된 일자 (YYYY-MM-DD) — 미지정 시 첫째 날 (게스트 동작 불변) */
  selectedDate?: string;
  /** [member 옵셔널 확장] 주간 스트립 일자 이동 (FR-205) */
  onSelectDate?: (date: string) => void;
  /** [member 옵셔널 확장] 전체 재생성 버튼 (FR-209) */
  onRegenerate?: () => void;
}

/** 일자(YYYY-MM-DD) → 일(day of month) 숫자 */
function dayOfMonth(date: string): number {
  return Number.parseInt(date.slice(8, 10), 10);
}

/**
 * 주간 식단 섹션 — 선택 일자(기본 오늘/첫째 날) 아침/점심/저녁 행 리스트 카드 + 주간 스트립 (FR-101/205).
 * 회원 모드에선 스트립이 일자 이동 버튼이 된다 (게스트는 표시 전용 — 불변).
 */
export function MealPlanSection({
  weekPlan,
  onRecipeClick,
  selectedDate,
  onSelectDate,
  onRegenerate,
}: MealPlanSectionProps) {
  const t = useTranslations('guestHome.mealPlan');
  const tPlan = useTranslations('memberHome.plan');

  const selectedIndex =
    selectedDate !== undefined ? weekPlan.findIndex((day) => day.date === selectedDate) : -1;
  const activeIndex = selectedIndex >= 0 ? selectedIndex : 0;
  const activeDay = weekPlan[activeIndex];

  return (
    <section id={MEAL_SECTION_ID} aria-label={t('title')} className="mt-1.5 flex flex-col gap-2.5">
      <div className="flex items-center justify-between px-0.5">
        <h2 className="text-base font-extrabold text-navy-900">{t('title')}</h2>
        {onRegenerate ? (
          <button
            type="button"
            onClick={onRegenerate}
            className="rounded-full bg-white px-3 py-1 text-xs font-bold text-brand-600 shadow-sm"
          >
            {tPlan('regenerate')}
          </button>
        ) : null}
      </div>
      <div className="rounded-[20px] bg-white px-4 py-1 shadow-card">
        {activeDay?.meals.map((meal) => (
          <MealCard key={meal.slot} meal={meal} onRecipeClick={onRecipeClick} />
        ))}
      </div>
      <ol aria-label={t('weekStrip')} className="flex gap-1.5 overflow-x-auto px-0.5 text-xs">
        {weekPlan.map((day, index) => {
          const isActive = index === activeIndex;
          const pillClass = `shrink-0 rounded-full px-2.5 py-1 font-semibold ${
            isActive ? 'bg-brand-600 font-bold text-white' : 'bg-white text-ink-400 shadow-sm'
          }`;
          const label =
            day.date !== undefined
              ? `${t(`day.${day.day}`)} ${dayOfMonth(day.date)}`
              : t(`day.${day.day}`);

          return (
            <li key={day.date ?? day.day} className="shrink-0">
              {day.date !== undefined && onSelectDate !== undefined ? (
                <button
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => onSelectDate(day.date as string)}
                  className={pillClass}
                >
                  {label}
                </button>
              ) : (
                <span className={pillClass}>{label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
