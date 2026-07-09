'use client';

import { useTranslations } from 'next-intl';
import { CUISINE_ART, CUISINE_IDS, DIRECTION_ART } from '@/features/household/constants';
import { MEAL_DIRECTIONS } from '@/features/guest/sampleMatrix';
import type { Cuisine } from '@/features/household/types';
import type { MealDirection } from '@/shared/api/types';

interface PreferenceStepProps {
  cuisines: Cuisine[];
  direction: MealDirection;
  submitting: boolean;
  onToggleCuisine: (cuisine: Cuisine) => void;
  onSelectDirection: (direction: MealDirection) => void;
  onPrev: () => void;
  onSubmit: () => void;
}

/** 음식 종류 아이콘 (프로토타입 cuisineChips SVG 6종) */
function CuisineIcon({ cuisine }: { cuisine: Cuisine }) {
  const color = CUISINE_ART[cuisine].color;
  switch (cuisine) {
    case 'korean':
      return (
        <svg aria-hidden width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path
            d="M3.5 12h17a8.5 8.5 0 0 1-8.5 7.5A8.5 8.5 0 0 1 3.5 12z"
            stroke={color}
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          <path d="M13 4.5l5 5M15 3.5l4.5 5" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    case 'western':
      return (
        <svg aria-hidden width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path
            d="M8 3v6.5a2 2 0 0 1-4 0V3M6 9.5V21"
            stroke={color}
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M17 3c-1.8 1.6-1.8 5.4 0 7v11"
            stroke={color}
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'japanese':
      return (
        <svg aria-hidden width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path
            d="M3 12c3-4.5 9-4.5 12 0-3 4.5-9 4.5-12 0z"
            stroke={color}
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          <path d="M15 12l5-3v6l-5-3z" stroke={color} strokeWidth="1.7" strokeLinejoin="round" />
          <circle cx="7.5" cy="11" r="1" fill={color} />
        </svg>
      );
    case 'chinese':
      return (
        <svg aria-hidden width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path d="M5.5 8.5h13L17 20H7L5.5 8.5z" stroke={color} strokeWidth="1.7" strokeLinejoin="round" />
          <path
            d="M4.5 8.5l3.5-4h8l3.5 4"
            stroke={color}
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'comfort':
      return (
        <svg aria-hidden width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path
            d="M3.5 13h17a8.5 8.5 0 0 1-8.5 7.5A8.5 8.5 0 0 1 3.5 13z"
            stroke={color}
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          <path
            d="M9 3.5c-1 1.5 1 2.5 0 4M15 3.5c-1 1.5 1 2.5 0 4"
            stroke={color}
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
      );
    case 'salad':
      return (
        <svg aria-hidden width="28" height="28" viewBox="0 0 24 24" fill="none">
          <path
            d="M20 4C9 4 4 9 4 20c11 0 16-5 16-16z"
            stroke={color}
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          <path d="M5 19C12 12 15 9.5 18 6.5" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
  }
}

/** 식단 방향 아이콘 (프로토타입 focusCards SVG 4종) */
function DirectionIcon({ direction }: { direction: MealDirection }) {
  const color = DIRECTION_ART[direction].color;
  switch (direction) {
    case 'health':
      return (
        <svg aria-hidden width="26" height="26" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 20.5C5.5 16 3 12.2 3 8.7 3 6.1 5 4 7.6 4c1.7 0 3.2.9 4.4 2.5C13.2 4.9 14.7 4 16.4 4 19 4 21 6.1 21 8.7c0 3.5-2.5 7.3-9 11.8z"
            stroke={color}
            strokeWidth="1.7"
            strokeLinejoin="round"
          />
          <path
            d="M8.5 11h2l1-2 1.5 3.5 1-1.5h1.5"
            stroke={color}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'diet':
      return (
        <svg aria-hidden width="26" height="26" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 3.5c2.8 3.6 4.6 5.6 4.6 8.6a4.6 4.6 0 0 1-9.2 0c0-1.4.6-2.6 1.5-3.7"
            stroke={color}
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M12 19v-4M10 16.5l2 1.7 2-1.7"
            stroke={color}
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      );
    case 'hearty':
      return (
        <svg aria-hidden width="26" height="26" viewBox="0 0 24 24" fill="none">
          <path d="M4 16a8 8 0 0 1 16 0z" stroke={color} strokeWidth="1.7" strokeLinejoin="round" />
          <path d="M3 16h18" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
          <path d="M12 8V6.3" stroke={color} strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      );
    case 'kids':
      return (
        <svg aria-hidden width="26" height="26" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.7" />
          <circle cx="9" cy="10.5" r="1" fill={color} />
          <circle cx="15" cy="10.5" r="1" fill={color} />
          <path d="M8.5 14.5a4 4 0 0 0 7 0" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
  }
}

/**
 * STEP 3/3 — 선호 음식(복수)·식단 방향(단일) 선택 (FR-313, 프로토타입 onboardStep 2 재현).
 */
export function PreferenceStep({
  cuisines,
  direction,
  submitting,
  onToggleCuisine,
  onSelectDirection,
  onPrev,
  onSubmit,
}: PreferenceStepProps) {
  const t = useTranslations('onboarding');
  const tCuisine = useTranslations('cuisine');

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="mb-2 text-xs font-extrabold tracking-wider text-brand-600">
        {t('stepIndicator', { current: 3 })}
      </p>
      <h1 className="text-[27px] font-extrabold leading-tight tracking-tight text-navy-900">
        {t('step3.title1')}
        <br />
        {t('step3.title2')}
      </h1>
      <p className="mt-2 text-sm font-medium text-ink-400">{t('step3.subtitle')}</p>

      {/* 음식 종류 · 복수 선택 */}
      <h2 className="mb-3 mt-6 text-[13.5px] font-extrabold text-ink-800">
        {t('step3.prefTitle')} <span className="font-semibold text-ink-300">{t('step3.prefMulti')}</span>
      </h2>
      <div className="grid grid-cols-3 gap-2.5">
        {CUISINE_IDS.map((cuisine) => {
          const selected = cuisines.includes(cuisine);
          return (
            <button
              key={cuisine}
              type="button"
              aria-pressed={selected}
              onClick={() => onToggleCuisine(cuisine)}
              className={`flex flex-col overflow-hidden rounded-2xl border-2 bg-white text-center ${
                selected
                  ? 'border-brand-600 shadow-[0_8px_20px_rgba(47,107,255,.18)]'
                  : 'border-[#ECEFF4] shadow-[0_1px_2px_rgba(16,30,60,.04)]'
              }`}
            >
              <span
                className="relative flex h-[58px] items-center justify-center"
                style={{ background: CUISINE_ART[cuisine].gradient }}
              >
                <CuisineIcon cuisine={cuisine} />
                {selected ? (
                  <span
                    aria-hidden
                    className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 shadow-[0_2px_6px_rgba(47,107,255,.4)]"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M5 13l4 4 10-11"
                        stroke="#fff"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                ) : null}
              </span>
              <span
                className={`px-1.5 py-2 text-[12.5px] font-bold ${
                  selected ? 'text-brand-600' : 'text-ink-800'
                }`}
              >
                {tCuisine(cuisine)}
              </span>
            </button>
          );
        })}
      </div>

      {/* 식단 방향 · 하나 선택 */}
      <h2 className="mb-3 mt-[26px] text-[13.5px] font-extrabold text-ink-800">
        {t('step3.dirTitle')} <span className="font-semibold text-ink-300">{t('step3.dirSingle')}</span>
      </h2>
      <div role="radiogroup" aria-label={t('step3.dirTitle')} className="flex flex-col gap-2.5">
        {MEAL_DIRECTIONS.map((key) => {
          const selected = direction === key;
          return (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onSelectDirection(key)}
              className={`flex items-center gap-[13px] rounded-2xl border-[1.5px] px-[13px] py-[11px] text-left ${
                selected ? 'border-brand-600 bg-brand-50' : 'border-transparent bg-[#F6F8FC]'
              }`}
            >
              <span
                aria-hidden
                className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-[13px]"
                style={{ background: DIRECTION_ART[key].gradient }}
              >
                <DirectionIcon direction={key} />
              </span>
              <span className="flex-1">
                <span className="block text-[15px] font-bold text-ink-800">
                  {t(`step3.direction.${key}.title`)}
                </span>
                <span className="block text-[12.5px] text-ink-400">
                  {t(`step3.direction.${key}.desc`)}
                </span>
              </span>
              <span
                aria-hidden
                className={`flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border-[1.5px] ${
                  selected ? 'border-brand-600 bg-brand-600' : 'border-[#C2C9D6] bg-white'
                }`}
              >
                {selected ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M5 13l4 4 10-11"
                      stroke="#fff"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>

      <div className="min-h-5 flex-1" />
      <div className="mt-2 flex gap-2.5">
        <button
          type="button"
          onClick={onPrev}
          disabled={submitting}
          className="rounded-2xl bg-[#F0F2F6] px-[22px] py-[17px] text-center text-base font-bold text-ink-500 disabled:opacity-60"
        >
          {t('step3.prev')}
        </button>
        <button
          type="button"
          onClick={onSubmit}
          disabled={submitting}
          className="flex-1 rounded-2xl bg-brand-600 py-[17px] text-center text-base font-bold text-white shadow-cta disabled:opacity-60"
        >
          {t('step3.cta')}
        </button>
      </div>
    </div>
  );
}
