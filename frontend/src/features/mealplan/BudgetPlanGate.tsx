'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { BudgetDraftFlow } from '@/features/guest/BudgetDraftFlow';
import type { CreateOnboardingPlanResult } from '@/features/budget/createOnboardingPlan';
import type { GuestPlan } from '@/features/guest/store';

interface BudgetPlanGateProps {
  /** 3스텝 완료 → POST /budget/plans source='onboarding' (FR-207) */
  onComplete: (plan: GuestPlan) => Promise<CreateOnboardingPlanResult['kind']>;
}

/**
 * 예산안 없는 회원 게이트 (FR-207) — 기존 BudgetDraftFlow 재사용해 서버 저장.
 */
export function BudgetPlanGate({ onComplete }: BudgetPlanGateProps) {
  const t = useTranslations('memberHome.budgetGate');
  const tCommon = useTranslations('common');
  const [flowOpen, setFlowOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  const handleComplete = async (plan: GuestPlan) => {
    setFlowOpen(false);
    setSaving(true);
    setFailed(false);
    const kind = await onComplete(plan);
    if (kind === 'invalid' || kind === 'error') setFailed(true);
    setSaving(false);
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col justify-center gap-3.5 bg-surface-app px-[18px] py-8 sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card">
      {failed ? (
        <p role="alert" className="rounded-[16px] bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {tCommon('error.fallback')}
        </p>
      ) : null}
      <section
        aria-label={t('title')}
        className="rounded-3xl bg-[linear-gradient(150deg,#1C2E58_0%,#0B1B3A_100%)] p-6 text-white shadow-hero"
      >
        <h1 className="text-[22px] font-extrabold leading-snug tracking-tight">{t('title')}</h1>
        <p className="mt-2 text-[13px] leading-relaxed text-white/70">{t('description')}</p>
        <button
          type="button"
          disabled={saving}
          onClick={() => setFlowOpen(true)}
          className="mt-6 w-full rounded-[16px] bg-mint-500 px-4 py-4 text-[15px] font-extrabold text-navy-900 shadow-cta disabled:opacity-60"
        >
          {t('cta')}
        </button>
      </section>
      <BudgetDraftFlow
        open={flowOpen}
        onClose={() => setFlowOpen(false)}
        onComplete={(plan) => void handleComplete(plan)}
      />
    </div>
  );
}
