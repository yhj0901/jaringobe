'use client';

import { useLocale, useTranslations } from 'next-intl';
import { formatMoney } from '@/shared/ui/MoneyText';
import { MOOD_ART } from '@/features/household/constants';
import { budgetMood, budgetRange, perPersonAmount } from '@/features/household/onboardingLogic';
import type { Money } from '@/shared/api/types';

interface BudgetStepProps {
  size: number;
  budget: number;
  currency: Money['currency'];
  locked: boolean;
  onBudgetChange: (value: number) => void;
  onToggleLock: () => void;
  onPrev: () => void;
  onNext: () => void;
}

/** 수준 피드백 아이콘 (프로토타입 isSafe/isCaution/isRisk SVG) */
function MoodIcon({ mood }: { mood: 'frugal' | 'moderate' | 'roomy' }) {
  const color = MOOD_ART[mood].color;
  if (mood === 'frugal') {
    return (
      <svg aria-hidden width="19" height="19" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 3l7 3v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3z"
          stroke={color}
          strokeWidth="1.9"
          strokeLinejoin="round"
        />
        <path d="M9 12l2 2 4-4.5" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (mood === 'moderate') {
    return (
      <svg aria-hidden width="19" height="19" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.9" />
        <path d="M12 8v5" stroke={color} strokeWidth="2" strokeLinecap="round" />
        <circle cx="12" cy="16.5" r="1.1" fill={color} />
      </svg>
    );
  }
  return (
    <svg aria-hidden width="19" height="19" viewBox="0 0 24 24" fill="none">
      <path d="M12 3l9.5 16.5H2.5L12 3z" stroke={color} strokeWidth="1.9" strokeLinejoin="round" />
      <path d="M12 9.5v4.5" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="17" r="1.1" fill={color} />
    </svg>
  );
}

/**
 * STEP 2/3 — 한 달 식비 예산 잠그기 (FR-312, 프로토타입 onboardStep 1 재현).
 * 대형 금액 + 인원 기반 슬라이더 + 수준 피드백 배너(알뜰/적정/여유) + 예산 락 토글.
 */
export function BudgetStep({
  size,
  budget,
  currency,
  locked,
  onBudgetChange,
  onToggleLock,
  onPrev,
  onNext,
}: BudgetStepProps) {
  const t = useTranslations('onboarding');
  const locale = useLocale();

  const range = budgetRange(size, currency);
  const mood = budgetMood(budget, size, currency);
  const art = MOOD_ART[mood];
  const money = (amount: number) => formatMoney({ amount: String(amount), currency }, locale);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="mb-2 text-xs font-extrabold tracking-wider text-brand-600">
        {t('stepIndicator', { current: 2 })}
      </p>
      <h1 className="text-[27px] font-extrabold leading-tight tracking-tight text-navy-900">
        {t('step2.title1')}
        <br />
        {t('step2.title2')}
      </h1>
      <p className="mt-2 text-sm font-medium text-ink-400">{t('step2.subtitle')}</p>

      {/* 대형 금액 + 요약 칩 */}
      <div className="mt-8 text-center">
        <p className="text-[13px] font-semibold text-ink-400">{t('step2.monthBudget')}</p>
        <p
          className="text-[48px] font-extrabold leading-[1.1] tracking-tight tabular-nums transition-colors"
          style={{ color: art.color }}
        >
          {money(budget)}
        </p>
        <span
          className="mt-2 inline-flex items-center gap-1.5 rounded-full px-3 py-[5px] text-xs font-extrabold"
          style={{ backgroundColor: art.bg, color: art.color }}
        >
          {t('step1.householdBadge', { count: size })} ·{' '}
          {t('step2.perPerson', { amount: money(perPersonAmount(budget, size)) })} ·{' '}
          {t('step2.recommended', { amount: money(range.rec) })}
        </span>
      </div>

      {/* 슬라이더 (min~max × 인원) */}
      <div className="mx-1 mb-1.5 mt-[22px]">
        <input
          type="range"
          aria-label={t('step2.sliderLabel')}
          min={range.min}
          max={range.max}
          step={range.step}
          value={budget}
          onChange={(event) => onBudgetChange(Number(event.target.value))}
          className="w-full accent-brand-600"
        />
        <div className="mt-2 flex justify-between text-[11.5px] font-semibold text-[#B0B9C9]">
          <span>{money(range.min)}</span>
          <span>{money(range.max)}</span>
        </div>

        {/* 수준 피드백 배너 (알뜰/적정/여유) */}
        <div
          role="status"
          className="mt-3.5 flex items-center gap-[11px] rounded-[14px] px-[15px] py-[13px]"
          style={{ backgroundColor: art.bg }}
        >
          <span className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-white">
            <MoodIcon mood={mood} />
          </span>
          <div className="flex-1">
            <p className="text-sm font-extrabold" style={{ color: art.color }}>
              {t(`step2.mood.${mood}.title`)}
            </p>
            <p className="mt-px text-[11.5px] opacity-85" style={{ color: art.color }}>
              {t(`step2.mood.${mood}.desc`)}
            </p>
          </div>
        </div>
        <p className="mt-2.5 text-center text-[11.5px] font-semibold text-ink-300">
          {t('step2.minNote', {
            perPerson: money(range.min / size),
            count: size,
            total: money(range.min),
          })}
        </p>
      </div>

      {/* 예산 락 토글 */}
      <button
        type="button"
        role="switch"
        aria-checked={locked}
        aria-label={t('step2.lockName')}
        onClick={onToggleLock}
        className={`mt-7 flex items-center justify-between rounded-2xl border-[1.5px] px-[18px] py-4 text-left ${
          locked ? 'border-brand-600 bg-brand-50' : 'border-[#E3E9F5] bg-[#F0F2F6]'
        }`}
      >
        <span className="flex items-center gap-[11px]">
          <svg aria-hidden width="20" height="20" viewBox="0 0 24 24" fill="none">
            <rect
              x="4"
              y="10"
              width="16"
              height="11"
              rx="2.5"
              stroke={locked ? '#2F6BFF' : '#9AA6BD'}
              strokeWidth="2"
            />
            <path
              d="M8 10V7a4 4 0 0 1 8 0v3"
              stroke={locked ? '#2F6BFF' : '#9AA6BD'}
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span>
            <span className="block text-[14.5px] font-bold text-ink-800">{t('step2.lockName')}</span>
            <span className="block text-[11.5px] text-ink-400">
              {locked ? t('step2.lockOn') : t('step2.lockOff')}
            </span>
          </span>
        </span>
        <span
          aria-hidden
          className={`box-border flex h-7 w-12 rounded-full p-[3px] transition-all ${
            locked ? 'justify-end bg-brand-600' : 'justify-start bg-[#C2C9D6]'
          }`}
        >
          <span className="h-[22px] w-[22px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,.2)]" />
        </span>
      </button>

      <div className="flex-1" />
      <div className="mt-4 flex gap-2.5">
        <button
          type="button"
          onClick={onPrev}
          className="rounded-2xl bg-[#F0F2F6] px-[22px] py-[17px] text-center text-base font-bold text-ink-500"
        >
          {t('step2.prev')}
        </button>
        <button
          type="button"
          onClick={onNext}
          className="flex-1 rounded-2xl bg-brand-600 py-[17px] text-center text-base font-bold text-white shadow-cta"
        >
          {t('step2.next')}
        </button>
      </div>
    </div>
  );
}
