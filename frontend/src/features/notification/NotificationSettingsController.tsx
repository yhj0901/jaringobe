'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from '@/i18n/routing';
import { isApp, sendToApp, BRIDGE_VERSION } from '@/shared/bridge';
import { useBridgeStore } from '@/shared/bridge/store';
import {
  REMINDER_DEFAULT_TIMES,
  REMINDER_TYPES,
} from '@/features/notification/constants';
import { useNotificationSettings } from '@/features/notification/useNotificationSettings';
import type { NotificationSetting, NotificationType, ReminderType } from '@/features/notification/types';

/** 토글 스위치 — 온보딩 예산 락 토글과 동일 패턴 (role="switch") */
function ToggleSwitch({
  label,
  checked,
  disabled,
  onToggle,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-[26px] w-[46px] shrink-0 rounded-full transition-colors disabled:opacity-60 ${
        checked ? 'bg-brand-600' : 'bg-[#D6DCE7]'
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-[3px] h-5 w-5 rounded-full bg-white shadow transition-all ${
          checked ? 'left-[23px]' : 'left-[3px]'
        }`}
      />
    </button>
  );
}

/**
 * 알림 설정 화면 (`/settings/notifications`, ui-design 12장 — FR-003/007)
 * ① 식단 완성 토글 ② 식사 리마인더 3행(토글+HH:MM) ③ 웹 브라우저 안내 카드
 * ④ 앱 내 OS 권한 거부 배너(OPEN_OS_SETTINGS). 행 단위 즉시 저장.
 */
export function NotificationSettingsController() {
  const t = useTranslations('notification.settings');
  const tMeal = useTranslations('mealplan.mealType');
  const router = useRouter();
  const state = useNotificationSettings();
  const permission = useBridgeStore((store) => store.permission);
  const inApp = isApp();

  // 미인증(쿠키 무효 401) — 세션 만료 케이스 → 로그인으로 (ui-design 1장 규칙)
  useEffect(() => {
    if (state.status === 'unauthenticated') {
      router.replace('/login?next=/settings/notifications');
    }
  }, [state.status, router]);

  if (state.status === 'loading' || state.status === 'unauthenticated') {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label={t('loading')}
        className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col gap-3.5 bg-surface-app px-[18px] pb-6 pt-8 sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card"
      >
        <div aria-hidden className="h-[70px] animate-pulse rounded-[18px] bg-white shadow-card" />
        <div aria-hidden className="h-[200px] animate-pulse rounded-[18px] bg-white shadow-card" />
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col items-center justify-center gap-4 bg-surface-app px-[18px] sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card">
        <p role="alert" className="text-center text-sm font-semibold text-ink-600">
          {t('error.load')}
        </p>
        <button
          type="button"
          onClick={state.reload}
          className="rounded-2xl bg-brand-600 px-6 py-3 text-sm font-extrabold text-white shadow-cta"
        >
          {t('error.reload')}
        </button>
      </div>
    );
  }

  const byType = new Map<NotificationType, NotificationSetting>(
    state.settings.map((setting) => [setting.type, setting]),
  );
  const doneSetting = byType.get('mealplan_done');

  const reminderLabel = (type: ReminderType): string => {
    if (type === 'meal_reminder_breakfast') return tMeal('breakfast');
    if (type === 'meal_reminder_lunch') return tMeal('lunch');
    return tMeal('dinner');
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col bg-surface-app sm:min-h-0 sm:my-6 sm:overflow-hidden sm:rounded-[32px] sm:shadow-card">
      {/* 헤더 — 뒤로가기(설정) + 타이틀 (설정 페이지 9장과 동일 패턴) */}
      <header className="flex items-center gap-3 border-b border-[#EEF1F6] bg-white px-[18px] pb-3.5 pt-8">
        <button
          type="button"
          aria-label={t('backLabel')}
          onClick={() => router.push('/settings')}
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-surface-app"
        >
          <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path
              d="M15 5l-7 7 7 7"
              stroke="#16223B"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        <h1 className="text-[19px] font-extrabold tracking-tight text-navy-900">{t('title')}</h1>
      </header>

      <main className="flex-1 px-[18px] pb-8 pt-[18px]">
        {/* ④ 앱 내 + OS 권한 거부 배너 → OPEN_OS_SETTINGS (ui-design 12장) */}
        {inApp && permission === 'denied' ? (
          <div
            role="alert"
            className="mb-3.5 flex items-center justify-between gap-3 rounded-2xl border border-flame-200 bg-white p-4 shadow-card"
          >
            <p className="text-[13px] font-semibold text-ink-600">{t('permissionBanner.message')}</p>
            <button
              type="button"
              onClick={() =>
                sendToApp({ v: BRIDGE_VERSION, type: 'OPEN_OS_SETTINGS', payload: {} })
              }
              className="shrink-0 rounded-[12px] bg-brand-600 px-4 py-2 text-xs font-extrabold text-white"
            >
              {t('permissionBanner.openSettings')}
            </button>
          </div>
        ) : null}

        {/* 저장 실패 배너 — 롤백 후 안내 */}
        {state.updateError ? (
          <div
            role="alert"
            className="mb-3.5 flex items-start justify-between gap-3 rounded-2xl border border-flame-200 bg-white p-4 shadow-card"
          >
            <p className="text-[13px] font-semibold text-ink-600">{t('error.update')}</p>
            <button
              type="button"
              onClick={state.dismissError}
              className="shrink-0 rounded-[10px] bg-[#F0F2F6] px-3 py-1.5 text-xs font-bold text-ink-500"
            >
              {t('error.dismiss')}
            </button>
          </div>
        ) : null}

        {/* ③ 앱 미설치(웹 브라우저) 안내 카드 */}
        {!inApp ? (
          <div className="mb-3.5 rounded-2xl bg-navy-900/5 p-4">
            <p className="text-[13.5px] font-bold text-navy-900">{t('webNotice.title')}</p>
            <p className="mt-1 text-xs leading-relaxed text-ink-500">{t('webNotice.description')}</p>
          </div>
        ) : null}

        {/* ① 식단 완성 알림 */}
        <section aria-label={t('sectionDone')}>
          <h2 className="mx-0.5 mb-2 text-xs font-extrabold tracking-wide text-ink-400">
            {t('sectionDone')}
          </h2>
          <div className="rounded-[18px] bg-white px-4 shadow-card">
            <div className="flex items-center gap-3 py-3.5">
              <span className="min-w-0 flex-1">
                <span className="block text-[14.5px] font-bold text-ink-800">
                  {t('mealplanDone.title')}
                </span>
                <span className="block text-xs text-ink-300">{t('mealplanDone.description')}</span>
              </span>
              <ToggleSwitch
                label={t('mealplanDone.title')}
                checked={doneSetting?.enabled ?? false}
                disabled={doneSetting === undefined || state.savingTypes.has('mealplan_done')}
                onToggle={() =>
                  void state.update('mealplan_done', { enabled: !(doneSetting?.enabled ?? false) })
                }
              />
            </div>
          </div>
        </section>

        {/* ② 식사 리마인더 3행 — 토글 + HH:MM 피커 */}
        <section aria-label={t('sectionReminder')} className="mt-[22px]">
          <h2 className="mx-0.5 mb-2 text-xs font-extrabold tracking-wide text-ink-400">
            {t('sectionReminder')}
          </h2>
          <div className="rounded-[18px] bg-white px-4 shadow-card">
            {REMINDER_TYPES.map((type, index) => {
              const setting = byType.get(type);
              const enabled = setting?.enabled ?? false;
              const time = setting?.localTime ?? REMINDER_DEFAULT_TIMES[type];
              const saving = state.savingTypes.has(type);
              const label = reminderLabel(type);
              return (
                <div
                  key={type}
                  className={`flex items-center gap-3 py-3.5 ${
                    index < REMINDER_TYPES.length - 1 ? 'border-b border-[#F1F3F8]' : ''
                  }`}
                >
                  <span className="block min-w-0 flex-1 text-[14.5px] font-bold text-ink-800">
                    {label}
                  </span>
                  <input
                    type="time"
                    aria-label={t('reminder.timeLabel', { meal: label })}
                    value={time}
                    disabled={setting === undefined || !enabled || saving}
                    onChange={(event) => {
                      if (event.target.value !== '') {
                        void state.update(type, { localTime: event.target.value });
                      }
                    }}
                    className="rounded-[10px] bg-surface-app px-2.5 py-1.5 text-[13px] font-bold text-navy-900 disabled:opacity-50"
                  />
                  <ToggleSwitch
                    label={t('reminder.toggleLabel', { meal: label })}
                    checked={enabled}
                    disabled={setting === undefined || saving}
                    onToggle={() => void state.update(type, { enabled: !enabled })}
                  />
                </div>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
}
