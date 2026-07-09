'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';
import { Stepper } from '@/shared/ui/Stepper';
import {
  MEALPLAN_DAYS_DEFAULT,
  MEALPLAN_DAYS_MAX,
  MEALPLAN_DAYS_MIN,
} from '@/features/mealplan/constants';
import {
  validateChipItem,
  type ChipValidationError,
} from '@/features/mealplan/planCreateValidation';
import type { PlanCreateInput } from '@/features/mealplan/useMemberHome';

interface PlanCreateSheetProps {
  open: boolean;
  onClose: () => void;
  /** 생성 진행 중 — 제출 버튼 비활성 (연타 방지, FR-204) */
  busy?: boolean;
  onSubmit: (input: PlanCreateInput) => void;
}

const ERROR_KEY: Record<Exclude<ChipValidationError, 'empty'>, string> = {
  'too-long': 'errorTooLong',
  'too-many': 'errorTooMany',
  duplicate: 'errorDuplicate',
};

interface ChipFieldProps {
  id: string;
  label: string;
  placeholder: string;
  items: string[];
  onChange: (next: string[]) => void;
}

/** 칩 입력 필드 — 항목 30자/최대 10개 클라이언트 검증 (FR-203, CWE-79 길이·개수 제한) */
function ChipField({ id, label, placeholder, items, onChange }: ChipFieldProps) {
  const t = useTranslations('memberHome.create');
  const [value, setValue] = useState('');
  const [error, setError] = useState<Exclude<ChipValidationError, 'empty'> | null>(null);

  const addItem = () => {
    const result = validateChipItem(value, items);
    if (!result.ok) {
      // 빈 입력은 조용히 무시, 나머지는 에러 문구 표시
      setError(result.error === 'empty' ? null : result.error);
      return;
    }
    onChange([...items, result.value]);
    setValue('');
    setError(null);
  };

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-semibold text-ink-600">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          type="text"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            setError(null);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              addItem();
            }
          }}
          placeholder={placeholder}
          aria-invalid={error !== null}
          className="min-w-0 flex-1 rounded-2xl border border-[#E1E6EF] bg-white px-4 py-2.5 text-sm text-ink-800 focus:border-brand-600 focus:outline-none"
        />
        <button
          type="button"
          onClick={addItem}
          className="shrink-0 rounded-2xl bg-[#F0F2F6] px-4 py-2.5 text-sm font-bold text-ink-600"
        >
          {t('add')}
        </button>
      </div>
      {error !== null ? (
        <p role="alert" className="text-xs font-semibold text-red-600">
          {t(ERROR_KEY[error])}
        </p>
      ) : null}
      {items.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <li key={item}>
              <button
                type="button"
                aria-label={t('remove', { item })}
                onClick={() => onChange(items.filter((existing) => existing !== item))}
                className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-bold text-brand-700"
              >
                {item}
                <span aria-hidden>✕</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * 식단 생성 시트 (FR-203) — 기간 스테퍼(기본 7일) + 알레르기/선호 칩 입력(선택).
 * 자동 생성 트리거 금지 — 명시적 생성 버튼만 (LLM 비용).
 */
export function PlanCreateSheet({ open, onClose, busy = false, onSubmit }: PlanCreateSheetProps) {
  const t = useTranslations('memberHome.create');
  const [days, setDays] = useState<number>(MEALPLAN_DAYS_DEFAULT);
  const [allergies, setAllergies] = useState<string[]>([]);
  const [preferences, setPreferences] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setDays(MEALPLAN_DAYS_DEFAULT);
      setAllergies([]);
      setPreferences([]);
    }
  }, [open]);

  return (
    <BottomSheet open={open} onClose={onClose} labelledBy="plan-create-title">
      <div className="flex max-h-[75vh] flex-col gap-5 overflow-y-auto pb-1">
        <h2 id="plan-create-title" className="text-lg font-extrabold tracking-tight text-navy-900">
          {t('title')}
        </h2>

        <section className="flex flex-col gap-3">
          <h3 className="text-sm font-bold text-navy-900">{t('daysTitle')}</h3>
          <div className="flex items-center gap-3">
            <Stepper
              value={days}
              min={MEALPLAN_DAYS_MIN}
              max={MEALPLAN_DAYS_MAX}
              onChange={setDays}
              label={t('daysLabel')}
              decrementLabel={t('daysDecrement')}
              incrementLabel={t('daysIncrement')}
            />
            <span className="text-sm font-bold text-ink-500">{t('daysUnit', { days })}</span>
          </div>
        </section>

        <ChipField
          id="plan-create-allergies"
          label={t('allergiesLabel')}
          placeholder={t('allergiesPlaceholder')}
          items={allergies}
          onChange={setAllergies}
        />
        <ChipField
          id="plan-create-preferences"
          label={t('preferencesLabel')}
          placeholder={t('preferencesPlaceholder')}
          items={preferences}
          onChange={setPreferences}
        />

        <p className="text-[11.5px] leading-relaxed text-ink-300">{t('privacyNote')}</p>

        <button
          type="button"
          disabled={busy}
          onClick={() => onSubmit({ days, allergies, preferences })}
          className="rounded-2xl bg-brand-600 px-4 py-3.5 text-sm font-extrabold text-white shadow-cta disabled:opacity-60"
        >
          {t('submit')}
        </button>
      </div>
    </BottomSheet>
  );
}
