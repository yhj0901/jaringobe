'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import type { CycleStage, CycleState } from '@/features/cycle/types';
import type { OrderBlockedReason } from '@/features/order/types';

const STAGE_KEYS: Record<CycleStage, string> = {
  idle: 'idle',
  generating: 'generating',
  generated: 'generated',
  generate_failed: 'generateFailed',
  drafted: 'drafted',
  awaiting_user: 'awaitingUser',
  confirmed: 'confirmed',
  delivered: 'delivered',
  nothing_to_order: 'nothingToOrder',
  skipped_user: 'skippedUser',
  skipped_dormant: 'skippedDormant',
  deferred_quota: 'deferredQuota',
  paused: 'paused',
};

export const DORMANT_DISMISSED_PREFIX = 'cycle.dormantDismissed:';

function formatLocalDateTime(iso: string | null, locale: string): string {
  if (iso === null) return '';
  return new Intl.DateTimeFormat(locale === 'en' ? 'en-US' : 'ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso));
}

interface CycleStatusCardProps {
  cycle: CycleState;
  busy?: boolean;
  notice?: string | null;
  onApprove: () => void;
  onViewOrder: () => void;
  onSkip: () => void;
  onCreateNow: () => void;
  onViewMealPlan: () => void;
  onViewFridge: () => void;
  onGoSettings: () => void;
  onCancelOrder: () => void;
}

/** 홈 사이클 카드 — 서버가 준 stage 하나만으로 분기한다 (ui-design 14-2). */
export function CycleStatusCard({
  cycle,
  busy = false,
  notice = null,
  onApprove,
  onViewOrder,
  onSkip,
  onCreateNow,
  onViewMealPlan,
  onViewFridge,
  onGoSettings,
  onCancelOrder,
}: CycleStatusCardProps) {
  const t = useTranslations('cycle');
  const locale = useLocale();
  const [dormantDismissed, setDormantDismissed] = useState(false);

  useEffect(() => {
    const key = `${DORMANT_DISMISSED_PREFIX}${cycle.cycleStart}`;
    setDormantDismissed(window.localStorage.getItem(key) === '1');
  }, [cycle.cycleStart]);

  if (cycle.stage === 'skipped_dormant' && dormantDismissed) return null;

  const stageKey = STAGE_KEYS[cycle.stage];
  const displayTime =
    cycle.stage === 'confirmed'
      ? formatLocalDateTime(cycle.draftOrder?.deliveryEta ?? null, locale)
      : formatLocalDateTime(cycle.nextRunAt, locale);
  const body = t(`stage.${stageKey}.body`, { time: displayTime });
  const autoConfirmLabel =
    cycle.stage === 'drafted' && cycle.draftOrder?.autoConfirmAt
      ? t('stage.drafted.autoConfirmAt', {
          time: formatLocalDateTime(cycle.draftOrder.autoConfirmAt, locale),
        })
      : null;

  const dismissDormant = () => {
    window.localStorage.setItem(`${DORMANT_DISMISSED_PREFIX}${cycle.cycleStart}`, '1');
    setDormantDismissed(true);
  };

  return (
    <section
      aria-label={t('card.title')}
      aria-live="polite"
      aria-busy={cycle.stage === 'generating' || busy || undefined}
      className="rounded-[20px] border border-brand-100 bg-white p-4 shadow-card"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-lg"
        >
          ↻
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-extrabold tracking-wide text-brand-600">
            {t('card.title')}
          </p>
          <h2 className="mt-0.5 text-[14.5px] font-extrabold text-navy-900">
            {t(`stage.${stageKey}.title`)}
          </h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-500">{body}</p>
          {autoConfirmLabel ? (
            <p className="mt-2 text-xs font-bold text-brand-700">{autoConfirmLabel}</p>
          ) : null}
        </div>
      </div>

      {cycle.stage === 'awaiting_user' && cycle.draftOrder?.blockedReason ? (
        <BlockedBanner
          reason={cycle.draftOrder.blockedReason}
          busy={busy}
          onApprove={onApprove}
          onViewOrder={onViewOrder}
          onCreateNow={onCreateNow}
          onGoSettings={onGoSettings}
        />
      ) : null}

      {notice ? (
        <p role="status" className="mt-3 rounded-xl bg-brand-50 px-3 py-2 text-xs font-bold text-brand-700">
          {notice}
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {cycle.stage === 'generated' ? (
          <Action label={t('cta.viewMealPlan')} onClick={onViewMealPlan} />
        ) : null}
        {cycle.stage === 'generate_failed' ? (
          <Action label={t('cta.createNow')} onClick={onCreateNow} />
        ) : null}
        {cycle.stage === 'drafted' ? (
          <>
            <Action label={t('cta.approve')} onClick={onApprove} disabled={busy} />
            <Action label={t('cta.view')} onClick={onViewOrder} secondary />
            <Action label={t('cta.skip')} onClick={onSkip} disabled={busy} secondary />
          </>
        ) : null}
        {cycle.stage === 'confirmed' ? (
          <>
            <Action label={t('cta.view')} onClick={onViewOrder} />
            <Action label={t('cta.cancelOrder')} onClick={onCancelOrder} disabled={busy} secondary />
          </>
        ) : null}
        {cycle.stage === 'nothing_to_order' ? (
          <Action label={t('cta.viewFridge')} onClick={onViewFridge} />
        ) : null}
        {cycle.stage === 'skipped_dormant' ? (
          <>
            <Action label={t('dormant.cta')} onClick={onCreateNow} />
            <Action label={t('cta.dismiss')} onClick={dismissDormant} secondary />
          </>
        ) : null}
        {cycle.stage === 'paused' ? (
          <Action label={t('cta.goSettings')} onClick={onGoSettings} />
        ) : null}
      </div>
    </section>
  );
}

function BlockedBanner({
  reason,
  busy,
  onApprove,
  onViewOrder,
  onCreateNow,
  onGoSettings,
}: {
  reason: OrderBlockedReason;
  busy: boolean;
  onApprove: () => void;
  onViewOrder: () => void;
  onCreateNow: () => void;
  onGoSettings: () => void;
}) {
  const t = useTranslations('cycle');
  const action =
    reason === 'AUTO_CONFIRM_OFF' || reason === 'BUDGET_EXCEEDED'
      ? onApprove
      : reason === 'STORE_DISCONNECTED'
        ? onGoSettings
        : reason === 'MEALPLAN_OVER_BUDGET'
          ? onCreateNow
          : onViewOrder;
  return (
    <div role="alert" className="mt-3 rounded-xl border border-flame-200 bg-flame-50/40 p-3">
      <p className="text-xs font-extrabold text-navy-900">{t(`blocked.${reason}.title`)}</p>
      <button
        type="button"
        disabled={busy}
        onClick={action}
        className="mt-2 rounded-lg bg-navy-900 px-3 py-2 text-xs font-extrabold text-white disabled:opacity-50"
      >
        {t(`blocked.${reason}.cta`)}
      </button>
    </div>
  );
}

function Action({
  label,
  onClick,
  disabled = false,
  secondary = false,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-xl px-3.5 py-2.5 text-xs font-extrabold disabled:opacity-50 ${
        secondary ? 'bg-[#F0F2F6] text-ink-600' : 'bg-brand-600 text-white shadow-cta'
      }`}
    >
      {label}
    </button>
  );
}
