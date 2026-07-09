'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { GENERATION_STEP_INTERVAL_MS } from '@/features/mealplan/constants';

const STEP_KEYS = ['step1', 'step2', 'step3'] as const;

/**
 * 생성 로딩 연출 (FR-204) — 단계별 진행 문구 로테이션 + 스켈레톤, aria-busy/라이브 리전.
 * LLM 생성은 수 초~수십 초 — 비동기 UX 로 체감 완화.
 */
export function GenerationLoading() {
  const t = useTranslations('memberHome.loading');
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(
      () => setStepIndex((index) => (index + 1) % STEP_KEYS.length),
      GENERATION_STEP_INTERVAL_MS,
    );
    return () => clearInterval(timer);
  }, []);

  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-7 bg-surface-app/95 px-8 backdrop-blur-sm"
    >
      <div className="flex flex-col items-center gap-2 text-center">
        <h2 className="text-base font-extrabold tracking-tight text-navy-900">{t('title')}</h2>
        <p className="text-sm font-semibold text-ink-400">{t(STEP_KEYS[stepIndex] ?? 'step1')}</p>
      </div>
      {/* 스켈레톤 — 예산 히어로 + 식단 행 3개 실루엣 */}
      <div aria-hidden className="flex w-full max-w-[340px] flex-col gap-3">
        <div className="h-[120px] animate-pulse rounded-3xl bg-navy-900/10" />
        <div className="flex flex-col gap-2 rounded-[20px] bg-white p-4 shadow-card">
          <div className="h-4 w-1/2 animate-pulse rounded-full bg-[#E9EDF5]" />
          <div className="h-4 w-3/4 animate-pulse rounded-full bg-[#E9EDF5]" />
          <div className="h-4 w-2/3 animate-pulse rounded-full bg-[#E9EDF5]" />
        </div>
      </div>
    </div>
  );
}
