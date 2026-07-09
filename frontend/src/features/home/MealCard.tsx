import { useTranslations } from 'next-intl';
import { Badge } from '@/shared/ui/Badge';
import type { MealItem } from '@/features/home/types';

interface MealCardProps {
  meal: MealItem;
  /** 저장이 필요한 행동(전체 조리법 보기) 시 가입 게이트 (FR-109) */
  onRecipeClick?: () => void;
}

/** 식단 카드 — 슬롯 라벨 + 메뉴명 + "예시" 라벨 슬롯 (FR-101) */
export function MealCard({ meal, onRecipeClick }: MealCardProps) {
  const t = useTranslations('guestHome');

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">
          {t(`meal.slot.${meal.slot}`)}
        </span>
        {meal.isSample ? <Badge tone="neutral">{t('sampleLabel')}</Badge> : null}
      </div>
      <p className="text-sm font-semibold text-gray-900">{meal.name}</p>
      <button
        type="button"
        onClick={onRecipeClick}
        className="self-start text-xs font-medium text-brand-600 underline underline-offset-2"
      >
        {t('meal.viewRecipe')}
      </button>
    </article>
  );
}
