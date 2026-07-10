'use client';

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';
import { Badge } from '@/shared/ui/Badge';
import {
  RECIPE_DEFAULT_DIFFICULTY,
  RECIPE_DEFAULT_SERVINGS,
} from '@/features/mealplan/constants';
import type { MealItem } from '@/features/home/types';

interface RecipeSheetProps {
  /** 표시할 끼니 — null 이면 시트 닫힘 */
  meal: MealItem | null;
  /** 가구 인원 → "N인분" (FR-504). 미지정 시 기본값 폴백 */
  householdSize?: number;
  onClose: () => void;
}

const TITLE_ID = 'recipe-sheet-title';

/** 메타 3칩 공용 셀 */
function MetaChip({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1 rounded-[13px] bg-[#F6F8FC] px-2 py-2.5 text-center">
      {icon}
      <span className="text-[13px] font-extrabold text-ink-800">{label}</span>
    </div>
  );
}

/**
 * 레시피 바텀시트 (FR-504, ui-design 10장) — BottomSheet 재사용.
 * 끼니 배지 + "AI 추천 레시피" 배지 · 요리명 · 메타 3칩(시간/난이도/인분) ·
 * 재료 칩 · 조리 단계 번호 리스트 · 닫기. 프로토타입 recipe 시트 재현.
 * steps 부재(기존 플랜·게스트 샘플) 시 기본 조리법 3단계 고정 문구.
 */
export function RecipeSheet({ meal, householdSize, onClose }: RecipeSheetProps) {
  const t = useTranslations('mealplan.recipe');
  const tSlot = useTranslations('mealplan.mealType');

  if (meal === null) return null;

  const timeLabel =
    meal.timeMinutes != null && meal.timeMinutes > 0
      ? t('timeMinutes', { minutes: meal.timeMinutes })
      : t('timeDefault');
  const difficultyLabel = t(`difficulty.${meal.difficulty ?? RECIPE_DEFAULT_DIFFICULTY}`);
  const servings = householdSize != null && householdSize > 0 ? householdSize : RECIPE_DEFAULT_SERVINGS;
  const servingsLabel = t('servings', { count: servings });

  const ingredients = meal.recipeIngredients ?? [];
  // steps 없으면 기본 조리법(고정 3단계) — 기존 플랜·게스트 샘플 폴백
  const steps =
    meal.steps !== undefined && meal.steps.length > 0
      ? meal.steps
      : Object.values(t.raw('basicSteps') as Record<string, string>);

  return (
    <BottomSheet open onClose={onClose} labelledBy={TITLE_ID}>
      <div className="max-h-[70vh] overflow-y-auto">
        <div className="mb-1.5 flex items-center gap-2">
          <Badge tone="brand">{tSlot(meal.slot)}</Badge>
          <span className="inline-flex items-center rounded-full bg-[#E6F8F1] px-2 py-0.5 text-[11px] font-bold text-[#0A8A60]">
            {t('aiBadge')}
          </span>
        </div>
        <h2
          id={TITLE_ID}
          className="text-[22px] font-extrabold leading-tight tracking-tight text-navy-900"
        >
          {meal.name}
        </h2>

        <div className="my-4 flex gap-2">
          <MetaChip
            icon={
              <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="13" r="8" stroke="#2F6BFF" strokeWidth="1.8" />
                <path
                  d="M12 9v4l2.5 1.5M9 3h6"
                  stroke="#2F6BFF"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            }
            label={timeLabel}
          />
          <MetaChip
            icon={
              <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M4 18l4-9 4 5 3-7 5 11z"
                  stroke="#0FB07A"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
            }
            label={difficultyLabel}
          />
          <MetaChip
            icon={
              <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
                <circle cx="9" cy="9" r="3" stroke="#E0651A" strokeWidth="1.8" />
                <path
                  d="M3.5 19a5.5 5.5 0 0 1 11 0M16 6.5a3 3 0 0 1 0 5M17 19a5.5 5.5 0 0 0-2.5-4.6"
                  stroke="#E0651A"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            }
            label={servingsLabel}
          />
        </div>

        {ingredients.length > 0 ? (
          <>
            <h3 className="mb-2 text-[13.5px] font-extrabold text-ink-800">
              {t('ingredientsTitle')}
            </h3>
            <ul className="mb-5 flex flex-wrap gap-1.5">
              {ingredients.map((ingredient, index) => (
                <li
                  key={`${ingredient.name}-${index}`}
                  className="rounded-[10px] bg-[#F0F4FB] px-3 py-1.5 text-[12.5px] font-semibold text-[#3A4A66]"
                >
                  {ingredient.name} {ingredient.quantity}
                  {ingredient.unit}
                </li>
              ))}
            </ul>
          </>
        ) : null}

        <h3 className="mb-3 text-[13.5px] font-extrabold text-ink-800">{t('stepsTitle')}</h3>
        <ol className="flex flex-col gap-3">
          {steps.map((step, index) => (
            <li key={index} className="flex items-start gap-3">
              <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-navy-800 text-[12.5px] font-extrabold text-white">
                {index + 1}
              </span>
              <span className="flex-1 pt-0.5 text-[13.5px] leading-relaxed text-[#3A4A66]">
                {step}
              </span>
            </li>
          ))}
        </ol>

        <button
          type="button"
          onClick={onClose}
          className="mt-6 w-full rounded-[14px] bg-[#F0F2F6] py-4 text-[15px] font-bold text-ink-500"
        >
          {t('close')}
        </button>
      </div>
    </BottomSheet>
  );
}
