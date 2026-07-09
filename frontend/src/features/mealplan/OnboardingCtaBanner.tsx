'use client';

import { useTranslations } from 'next-intl';

interface OnboardingCtaBannerProps {
  /** setup: 온보딩 미완료 → /onboarding · create: 온보딩 완료 + 식단 없음 → 생성 시트 (FR-316) */
  variant: 'setup' | 'create';
  busy?: boolean;
  onClick: () => void;
}

/**
 * 샘플 홈 상단 고정 배너 (ui-design 8장) — 빈 히어로 전면 노출 대체.
 * 식단 없는 회원에게 샘플 홈 위에서 온보딩/생성을 유도한다.
 */
export function OnboardingCtaBanner({ variant, busy = false, onClick }: OnboardingCtaBannerProps) {
  const t = useTranslations('memberHome.banner');

  return (
    <div className="sticky top-2 z-40 mb-3.5 flex items-center justify-between gap-3 rounded-[18px] bg-[linear-gradient(150deg,#1C2E58_0%,#0B1B3A_100%)] px-4 py-3.5 shadow-hero">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 text-[11px] font-bold text-mint-300">
          <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none">
            <rect x="4" y="10" width="16" height="11" rx="2.5" stroke="#36E0A6" strokeWidth="2" />
            <path
              d="M8 10V7a4 4 0 0 1 8 0v3"
              stroke="#36E0A6"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          {t(`${variant}.badge`)}
        </p>
        <p className="mt-0.5 text-[13px] font-bold leading-snug text-white">
          {t(`${variant}.title`)}
        </p>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={onClick}
        className="shrink-0 rounded-[13px] bg-mint-500 px-3.5 py-2.5 text-[12.5px] font-extrabold text-navy-900 shadow-mint disabled:opacity-60"
      >
        {t(`${variant}.cta`)}
      </button>
    </div>
  );
}
