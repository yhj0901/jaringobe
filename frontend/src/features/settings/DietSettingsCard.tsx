'use client';

import { useTranslations } from 'next-intl';
import type { DietSection } from '@/features/settings/useSettings';

interface DietSettingsCardProps {
  householdSummary: string;
  preferenceSummary: string;
  budgetSummary: string;
  onEdit: (section: DietSection) => void;
}

/** 행 아이콘 3종 (프로토타입 settings myDietSection SVG) */
function RowIcon({ section }: { section: DietSection }) {
  switch (section) {
    case 'household':
      return (
        <span
          aria-hidden
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-brand-50"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="8" r="3" stroke="#2F6BFF" strokeWidth="1.8" />
            <path
              d="M3.5 19a5.5 5.5 0 0 1 11 0M16 6.5a3 3 0 0 1 0 5M17 19a5.5 5.5 0 0 0-2.5-4.6"
              stroke="#2F6BFF"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </span>
      );
    case 'preference':
      return (
        <span
          aria-hidden
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-mint-50"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 11h16a8 8 0 0 1-8 7.5A8 8 0 0 1 4 11z"
              stroke="#0A8A60"
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <path
              d="M9 4c-1 1.5 1 2.5 0 4M15 4c-1 1.5 1 2.5 0 4"
              stroke="#0A8A60"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </span>
      );
    case 'budget':
      return (
        <span
          aria-hidden
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-flame-50"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <rect x="3.5" y="6" width="17" height="12" rx="2.5" stroke="#C2761F" strokeWidth="1.8" />
            <circle cx="12" cy="12" r="2.4" stroke="#C2761F" strokeWidth="1.8" />
          </svg>
        </span>
      );
  }
}

/** 3행 순서 — 가구 구성 → 선호·방향 → 예산 (프로토타입 순서) */
const ROWS: readonly DietSection[] = ['household', 'preference', 'budget'];

/**
 * 내 식생활 설정 3행 (FR-402) — 현재값 요약 + 클릭 시 단일 편집 오버레이 (호출측).
 */
export function DietSettingsCard({
  householdSummary,
  preferenceSummary,
  budgetSummary,
  onEdit,
}: DietSettingsCardProps) {
  const t = useTranslations('settings.diet');
  const summaries: Record<DietSection, string> = {
    household: householdSummary,
    preference: preferenceSummary,
    budget: budgetSummary,
  };

  return (
    <section aria-label={t('section')} className="mt-[22px]">
      <h2 className="mx-0.5 mb-2 text-xs font-extrabold tracking-wide text-ink-400">
        {t('section')}
      </h2>
      <div className="rounded-[18px] bg-white px-4 py-1 shadow-card">
        {ROWS.map((section, index) => (
          <button
            key={section}
            type="button"
            onClick={() => onEdit(section)}
            className={`flex w-full items-center gap-3 py-3.5 text-left ${
              index < ROWS.length - 1 ? 'border-b border-[#F1F3F8]' : ''
            }`}
          >
            <RowIcon section={section} />
            <span className="min-w-0 flex-1">
              <span className="block text-[14.5px] font-bold text-ink-800">
                {t(`${section}Title`)}
              </span>
              <span className="block truncate text-xs text-ink-300">{summaries[section]}</span>
            </span>
            <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M9 6l6 6-6 6"
                stroke="#C2C9D6"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ))}
      </div>
    </section>
  );
}
