import { useTranslations } from 'next-intl';

interface OverBudgetBannerProps {
  /** 재생성 유도 CTA — 확인 다이얼로그를 여는 콜백 (FR-206/209) */
  onRegenerate: () => void;
  /** 생성 진행 중 연타 방지 */
  busy?: boolean;
}

/**
 * 예산 초과 배너 (FR-206) — withinBudget=false 시 초과 안내 + 재생성 유도.
 * 접근성: 색 단독 금지 — 경고 아이콘 병행, role="alert".
 */
export function OverBudgetBanner({ onRegenerate, busy = false }: OverBudgetBannerProps) {
  const t = useTranslations('memberHome.overBudget');

  return (
    <div
      role="alert"
      className="mb-3.5 flex flex-col gap-2.5 rounded-[16px] border border-flame-200 bg-flame-50 p-4"
    >
      <div className="flex items-center gap-2">
        <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 3l9.5 16.5H2.5L12 3z"
            stroke="#E0651A"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          <path d="M12 10v4" stroke="#E0651A" strokeWidth="2" strokeLinecap="round" />
          <circle cx="12" cy="17" r="1.1" fill="#E0651A" />
        </svg>
        <h2 className="text-sm font-extrabold text-flame-600">{t('title')}</h2>
      </div>
      <p className="text-[12.5px] leading-relaxed text-ink-600">{t('description')}</p>
      <button
        type="button"
        disabled={busy}
        onClick={onRegenerate}
        className="rounded-[12px] bg-flame-500 px-4 py-2.5 text-[13px] font-extrabold text-white disabled:opacity-60"
      >
        {t('regenerate')}
      </button>
    </div>
  );
}
