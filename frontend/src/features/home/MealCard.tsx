import { useLocale, useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import { MoneyText } from '@/shared/ui/MoneyText';
import type { MealItem, MealSlot } from '@/features/home/types';

interface MealCardProps {
  meal: MealItem;
  /** 저장이 필요한 행동(전체 조리법 보기) 시 가입 게이트 (FR-109) */
  onRecipeClick?: () => void;
}

/** 슬롯 도트 색 — 디자인 프로토타입의 아침/점심/저녁 마커 */
const SLOT_DOT: Record<MealSlot, string> = {
  breakfast: '#F2A93B',
  lunch: '#2F6BFF',
  dinner: '#15244A',
};

/**
 * 식단 행 — 슬롯 도트 + 라벨 + 메뉴명 + "예시" 라벨 + 조리법 칩 (FR-101).
 * 회원 데이터엔 재료 목록·추정 비용이 옵셔널로 붙는다 (FR-205).
 */
export function MealCard({ meal, onRecipeClick }: MealCardProps) {
  const t = useTranslations('guestHome');
  const tMealType = useTranslations('mealplan.mealType');
  const locale = useLocale();

  return (
    <article className="flex items-center gap-2.5 border-b border-[#F1F3F8] py-3 last:border-b-0">
      <span
        aria-hidden
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: SLOT_DOT[meal.slot] }}
      />
      <span className="w-8 shrink-0 text-xs font-bold text-ink-400">{tMealType(meal.slot)}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold text-ink-800">
          {meal.name}
          {meal.isSample ? <Badge className="ml-1.5 align-middle">{t('sampleLabel')}</Badge> : null}
        </span>
        {meal.ingredients !== undefined && meal.ingredients.length > 0 ? (
          <span className="mt-0.5 block truncate text-[11.5px] font-medium text-ink-300">
            {meal.ingredients.join(' · ')}
          </span>
        ) : null}
      </span>
      {meal.estCost !== undefined ? (
        <MoneyText
          money={meal.estCost}
          locale={locale}
          className="shrink-0 text-xs font-extrabold tabular-nums text-ink-500"
        />
      ) : null}
      <button
        type="button"
        onClick={onRecipeClick}
        className="shrink-0 whitespace-nowrap rounded-[9px] bg-brand-50 px-3 py-1.5 text-xs font-extrabold text-brand-600"
      >
        {t('meal.viewRecipe')}
      </button>
    </article>
  );
}
