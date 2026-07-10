import { useLocale, useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import { MoneyText } from '@/shared/ui/MoneyText';
import type { MealItem, MealSlot } from '@/features/home/types';

interface MealCardProps {
  meal: MealItem;
  /** 행 본문(요리명) 클릭 → 레시피 시트 오픈 (FR-504). 게스트=샘플, 회원=실 레시피 */
  onRecipeClick?: () => void;
  /** [member 전용] 완료 설정/해제 토글 (FR-501/503). 미지정(게스트) 시 완료 버튼 숨김 */
  onToggleComplete?: () => void;
  /** 완료 토글 진행 중 — 연타 방지로 버튼 비활성 (FR-503) */
  completePending?: boolean;
}

/** 슬롯 도트 색 — 디자인 프로토타입의 아침/점심/저녁 마커 */
const SLOT_DOT: Record<MealSlot, string> = {
  breakfast: '#F2A93B',
  lunch: '#2F6BFF',
  dinner: '#15244A',
};

/**
 * 식단 행 — 슬롯 도트 + 라벨 + 메뉴명(클릭 시 레시피 시트) + 추정 비용 + 완료 버튼 (FR-101/205/501/504).
 * 회원 데이터엔 재료 목록·추정 비용이 옵셔널로 붙는다 (FR-205).
 * 완료 버튼은 onToggleComplete 제공(=회원) 시에만 노출 — 게스트는 기존 게이트/샘플 흐름 유지.
 */
export function MealCard({ meal, onRecipeClick, onToggleComplete, completePending }: MealCardProps) {
  const t = useTranslations('guestHome');
  const tMealType = useTranslations('mealplan.mealType');
  const tCompletion = useTranslations('mealplan.completion');
  const tRecipe = useTranslations('mealplan.recipe');
  const locale = useLocale();

  const completed = meal.completedAt != null;

  return (
    <article className="flex items-center gap-2.5 border-b border-[#F1F3F8] py-3 last:border-b-0">
      <span
        aria-hidden
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: SLOT_DOT[meal.slot] }}
      />
      <span className="w-8 shrink-0 text-xs font-bold text-ink-400">{tMealType(meal.slot)}</span>
      <button
        type="button"
        onClick={onRecipeClick}
        aria-label={tRecipe('openAria', { meal: meal.name })}
        className="flex min-w-0 flex-1 flex-col items-start text-left"
      >
        <span className="flex w-full items-center gap-1">
          <span className="block truncate text-sm font-bold text-ink-800">{meal.name}</span>
          {meal.isSample ? <Badge className="align-middle">{t('sampleLabel')}</Badge> : null}
          <svg aria-hidden width="13" height="13" viewBox="0 0 24 24" fill="none" className="shrink-0">
            <path
              d="M9 6l6 6-6 6"
              stroke="#C2C9D6"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        {meal.ingredients !== undefined && meal.ingredients.length > 0 ? (
          <span className="mt-0.5 block truncate text-[11.5px] font-medium text-ink-300">
            {meal.ingredients.join(' · ')}
          </span>
        ) : null}
      </button>
      {meal.estCost !== undefined ? (
        <MoneyText
          money={meal.estCost}
          locale={locale}
          className="shrink-0 text-xs font-extrabold tabular-nums text-ink-500"
        />
      ) : null}
      {onToggleComplete !== undefined ? (
        <button
          type="button"
          onClick={onToggleComplete}
          disabled={completePending}
          aria-pressed={completed}
          aria-label={
            completed
              ? tCompletion('unmarkAria', { meal: meal.name })
              : tCompletion('markAria', { meal: meal.name })
          }
          className={
            completed
              ? 'flex shrink-0 items-center gap-1 whitespace-nowrap rounded-[9px] bg-brand-50 px-2.5 py-1.5 text-xs font-extrabold text-brand-600 disabled:opacity-60'
              : 'shrink-0 whitespace-nowrap rounded-[9px] bg-brand-600 px-3 py-1.5 text-xs font-extrabold text-white shadow-cta disabled:opacity-60'
          }
        >
          {completed ? (
            <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none">
              <path
                d="M5 12l4 4L19 7"
                stroke="currentColor"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : null}
          {completed ? tCompletion('completed') : tCompletion('complete')}
        </button>
      ) : null}
    </article>
  );
}
