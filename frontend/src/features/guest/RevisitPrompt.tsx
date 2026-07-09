'use client';

import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';

interface RevisitPromptProps {
  open: boolean;
  onLogin: () => void;
  /** 구경하기 — 닫고 게스트 홈 계속 (이후 기존 프롬프트 규칙 유지, FR-316) */
  onBrowse: () => void;
}

/** 로그아웃 이력 재방문 게스트 [로그인하기/구경하기] 바텀시트 (ui-design 8장, FR-316) */
export function RevisitPrompt({ open, onLogin, onBrowse }: RevisitPromptProps) {
  const t = useTranslations('entry.revisit');

  return (
    <BottomSheet open={open} onClose={onBrowse} labelledBy="revisit-prompt-title">
      <h2 id="revisit-prompt-title" className="mb-1.5 text-base font-extrabold text-navy-900">
        {t('title')}
      </h2>
      <p className="mb-4 text-[13px] leading-relaxed text-ink-500">{t('description')}</p>
      <div className="flex gap-2.5">
        <button
          type="button"
          onClick={onBrowse}
          className="flex-1 rounded-[14px] bg-[#F0F2F6] px-4 py-3.5 text-sm font-bold text-ink-500"
        >
          {t('browse')}
        </button>
        <button
          type="button"
          onClick={onLogin}
          className="flex-1 rounded-[14px] bg-brand-600 px-4 py-3.5 text-sm font-extrabold text-white shadow-cta"
        >
          {t('login')}
        </button>
      </div>
    </BottomSheet>
  );
}
