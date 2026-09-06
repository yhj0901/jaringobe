'use client';

import { useTranslations } from 'next-intl';
import { useCycle } from '@/features/cycle/useCycle';
import type { Country } from '@/shared/api/types';

const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6] as const;

function Toggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-label={label}
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-50 ${
        checked ? 'bg-brand-600' : 'bg-[#D6DCE7]'
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all ${
          checked ? 'left-6' : 'left-1'
        }`}
      />
    </button>
  );
}

/** 설정 페이지 자동 사이클 섹션 (ui-design 14-5). */
export function CycleSettingsCard({ country }: { country: Country | string }) {
  const t = useTranslations('cycle.settings');
  const tWeekday = useTranslations('cycle.weekday');
  const tCycleError = useTranslations('cycle.error');
  const tCommon = useTranslations('common');
  const state = useCycle();

  if (state.status === 'loading' || state.status === 'unauthenticated') {
    return (
      <section aria-label={t('section')} aria-busy="true" className="mt-[22px] rounded-[18px] bg-white p-4 shadow-card">
        <div aria-hidden className="h-28 animate-pulse rounded-xl bg-surface-app" />
      </section>
    );
  }

  if (state.status === 'error' || state.cycle === null) {
    return (
      <section aria-label={t('section')} className="mt-[22px] rounded-[18px] bg-white p-4 shadow-card">
        <h2 className="text-xs font-extrabold tracking-wide text-ink-400">{t('section')}</h2>
        <p role="alert" className="mt-3 text-xs font-semibold text-flame-500">{t('loadError')}</p>
        <button type="button" onClick={state.reload} className="mt-3 rounded-xl bg-brand-600 px-4 py-2 text-xs font-extrabold text-white">
          {t('retry')}
        </button>
      </section>
    );
  }

  const cycle = state.cycle;
  const errorMessage = state.errorCode
    ? state.errorCode === 'RATE_LIMITED' || state.errorCode === 'CYCLE_ALREADY_CONFIRMED'
      ? tCycleError(state.errorCode)
      : tCommon('error.fallback')
    : null;

  return (
    <section aria-label={t('section')} className="mt-[22px]">
      <h2 className="mx-0.5 mb-2 text-xs font-extrabold tracking-wide text-ink-400">{t('section')}</h2>
      <div className="rounded-[18px] bg-white p-4 shadow-card">
        {errorMessage ? <p role="alert" className="mb-3 text-xs font-semibold text-flame-500">{errorMessage}</p> : null}

        <div className="flex items-center justify-between gap-3 border-b border-[#F1F3F8] pb-3">
          <span>
            <span className="block text-sm font-bold text-ink-800">{t('enabled')}</span>
            <span className="block text-xs text-ink-300">{cycle.enabled ? t('enabledOn') : t('enabledOff')}</span>
          </span>
          <Toggle label={t('enabled')} checked={cycle.enabled} disabled={state.saving} onChange={(enabled) => void state.updateSettings({ enabled })} />
        </div>

        <fieldset disabled={state.saving} className="border-b border-[#F1F3F8] py-3">
          <legend className="text-sm font-bold text-ink-800">{t('frequency')}</legend>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {(['weekly', 'biweekly'] as const).map((frequency) => (
              <label key={frequency} className={`rounded-xl border px-3 py-2 text-center text-xs font-bold ${cycle.frequency === frequency ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-ink-100 text-ink-500'}`}>
                <input className="sr-only" type="radio" name="cycle-frequency" value={frequency} checked={cycle.frequency === frequency} onChange={() => void state.updateSettings({ frequency })} />
                {t(frequency === 'weekly' ? 'frequencyWeekly' : 'frequencyBiweekly')}
              </label>
            ))}
          </div>
          {country === 'US' ? <p className="mt-2 text-xs text-ink-400">{t('frequencyUsHint')}</p> : null}
          {cycle.frequency === 'biweekly' ? <p className="mt-2 text-xs font-semibold text-brand-700">{t('biweeklyGraceHint')}</p> : null}
        </fieldset>

        <fieldset disabled={state.saving} className="border-b border-[#F1F3F8] py-3">
          <legend className="text-sm font-bold text-ink-800">{t('anchorWeekday')}</legend>
          <div className="mt-2 grid grid-cols-7 gap-1">
            {WEEKDAYS.map((day) => (
              <button key={day} type="button" aria-pressed={cycle.anchorWeekday === day} onClick={() => void state.updateSettings({ anchorWeekday: day })} className={`rounded-lg py-2 text-xs font-extrabold ${cycle.anchorWeekday === day ? 'bg-brand-600 text-white' : 'bg-surface-app text-ink-500'}`}>
                {tWeekday(String(day))}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="flex items-center justify-between gap-3 py-3">
          <span>
            <span className="block text-sm font-bold text-ink-800">{t('autoConfirm')}</span>
            {!cycle.autoConfirm ? <span className="block text-xs text-ink-300">{t('autoConfirmOffHint')}</span> : null}
          </span>
          <Toggle label={t('autoConfirm')} checked={cycle.autoConfirm} disabled={state.saving} onChange={(autoConfirm) => void state.updateSettings({ autoConfirm })} />
        </div>
        <p className="rounded-xl bg-flame-50 px-3 py-2 text-xs font-semibold leading-relaxed text-ink-600">{t('autoConfirmPushNotice')}</p>
        <p className="mt-3 text-xs text-ink-400">{t('timezone')}: {cycle.timezone}</p>
      </div>
    </section>
  );
}
