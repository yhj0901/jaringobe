'use client';

import { useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Stepper } from '@/shared/ui/Stepper';
import { MoneyText } from '@/shared/ui/MoneyText';
import {
  BUDGET_PRESETS,
  HOUSEHOLD_MAX,
  HOUSEHOLD_MIN,
} from '@/shared/config/constants';
import { isValidBudgetAmount, isValidHouseholdSize } from '@/features/guest/budgetDraftValidation';
import { MEAL_DIRECTIONS } from '@/features/guest/sampleMatrix';
import type { GuestPlan } from '@/features/guest/store';
import type { AppLocale } from '@/i18n/routing';

interface BudgetDraftFlowProps {
  open: boolean;
  onClose: () => void;
  onComplete: (plan: GuestPlan) => void;
}

/**
 * 예산안 작성 3스텝 오버레이 (FR-104)
 * ① 가구 인원(1~10 스테퍼) → ② 월 예산(로캘 프리셋 + 직접 입력) → ③ 식단 방향 4종
 */
export function BudgetDraftFlow({ open, onClose, onComplete }: BudgetDraftFlowProps) {
  const t = useTranslations('budgetDraft');
  const locale = useLocale() as AppLocale;
  const preset = BUDGET_PRESETS[locale];

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [householdSize, setHouseholdSize] = useState(2);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [customAmount, setCustomAmount] = useState('');
  const [amountError, setAmountError] = useState(false);

  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    dialogRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      setStep(1);
      setSelectedPreset(null);
      setCustomAmount('');
      setAmountError(false);
    }
  }, [open]);

  if (!open) return null;

  const resolvedAmount = customAmount !== '' ? customAmount.replace(/[,\s]/g, '') : selectedPreset;
  const amountValid = resolvedAmount !== null && isValidBudgetAmount(resolvedAmount, preset.currency);

  const goNextFromBudget = () => {
    if (!amountValid) {
      setAmountError(true);
      return;
    }
    setAmountError(false);
    setStep(3);
  };

  const completeWithDirection = (direction: GuestPlan['mealDirection']) => {
    if (!amountValid || resolvedAmount === null || !isValidHouseholdSize(householdSize)) return;
    onComplete({
      householdSize,
      amount: resolvedAmount,
      currency: preset.currency,
      mealDirection: direction,
    });
  };

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="budget-draft-title"
      tabIndex={-1}
      className="fixed inset-0 z-50 flex flex-col bg-white p-5 outline-none"
    >
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 pt-8">
        <header className="flex items-center justify-between">
          <h2 id="budget-draft-title" className="text-lg font-bold text-gray-900">
            {t('title')}
          </h2>
          <button type="button" onClick={onClose} aria-label={t('closeLabel')} className="p-2 text-gray-500">
            ✕
          </button>
        </header>

        <p className="text-sm text-gray-500" aria-live="polite">
          {t('stepIndicator', { step, total: 3 })}
        </p>

        {step === 1 ? (
          <section className="flex flex-col gap-5">
            <h3 className="text-base font-semibold text-gray-900">{t('step1.title')}</h3>
            <Stepper
              value={householdSize}
              min={HOUSEHOLD_MIN}
              max={HOUSEHOLD_MAX}
              onChange={setHouseholdSize}
              label={t('step1.label')}
              decrementLabel={t('step1.decrement')}
              incrementLabel={t('step1.increment')}
            />
            <button
              type="button"
              onClick={() => setStep(2)}
              className="rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
            >
              {t('next')}
            </button>
          </section>
        ) : null}

        {step === 2 ? (
          <section className="flex flex-col gap-4">
            <h3 className="text-base font-semibold text-gray-900">{t('step2.title')}</h3>
            <div role="radiogroup" aria-label={t('step2.presetsLabel')} className="grid grid-cols-2 gap-2">
              {preset.amounts.map((amount) => (
                <button
                  key={amount}
                  type="button"
                  role="radio"
                  aria-checked={selectedPreset === amount && customAmount === ''}
                  onClick={() => {
                    setSelectedPreset(amount);
                    setCustomAmount('');
                    setAmountError(false);
                  }}
                  className={`rounded-xl border px-4 py-3 text-sm font-semibold ${
                    selectedPreset === amount && customAmount === ''
                      ? 'border-brand-600 bg-brand-50 text-brand-700'
                      : 'border-gray-300 text-gray-700'
                  }`}
                >
                  <MoneyText money={{ amount, currency: preset.currency }} locale={locale} />
                </button>
              ))}
            </div>
            <label className="flex flex-col gap-1 text-sm text-gray-700">
              {t('step2.customLabel')}
              <input
                type="text"
                inputMode="numeric"
                value={customAmount}
                onChange={(event) => {
                  setCustomAmount(event.target.value);
                  setAmountError(false);
                }}
                placeholder={t('step2.customPlaceholder')}
                aria-invalid={amountError}
                className="rounded-xl border border-gray-300 px-4 py-3"
              />
            </label>
            {amountError ? (
              <p role="alert" className="text-sm text-red-600">
                {t('step2.invalidRange')}
              </p>
            ) : null}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="flex-1 rounded-xl border border-gray-300 px-4 py-3 text-sm font-medium text-gray-700"
              >
                {t('back')}
              </button>
              <button
                type="button"
                onClick={goNextFromBudget}
                className="flex-1 rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
              >
                {t('next')}
              </button>
            </div>
          </section>
        ) : null}

        {step === 3 ? (
          <section className="flex flex-col gap-4">
            <h3 className="text-base font-semibold text-gray-900">{t('step3.title')}</h3>
            <div className="grid grid-cols-2 gap-2">
              {MEAL_DIRECTIONS.map((direction) => (
                <button
                  key={direction}
                  type="button"
                  onClick={() => completeWithDirection(direction)}
                  className="rounded-xl border border-gray-300 px-4 py-4 text-sm font-semibold text-gray-800 hover:border-brand-600"
                >
                  {t(`direction.${direction}`)}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setStep(2)}
              className="rounded-xl border border-gray-300 px-4 py-3 text-sm font-medium text-gray-700"
            >
              {t('back')}
            </button>
          </section>
        ) : null}
      </div>
    </div>
  );
}
