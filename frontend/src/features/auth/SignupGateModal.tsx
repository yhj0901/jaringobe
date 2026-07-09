'use client';

import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';

interface SignupGateModalProps {
  open: boolean;
  onLogin: () => void;
  onClose: () => void;
}

/** 쓰기 행동(식사 완료 체크·전체 조리법 보기 등) 공통 가입 게이트 (FR-109) */
export function SignupGateModal({ open, onLogin, onClose }: SignupGateModalProps) {
  const t = useTranslations('auth.gate');

  return (
    <BottomSheet open={open} onClose={onClose} labelledBy="signup-gate-title">
      <h2 id="signup-gate-title" className="mb-2 text-base font-extrabold text-navy-900">
        {t('title')}
      </h2>
      <p className="mb-4 text-sm leading-relaxed text-ink-500">{t('description')}</p>
      <div className="flex gap-2.5">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-[14px] bg-[#F0F2F6] px-4 py-3.5 text-sm font-bold text-ink-500"
        >
          {t('later')}
        </button>
        <button
          type="button"
          onClick={onLogin}
          className="flex-1 rounded-[14px] bg-brand-600 px-4 py-3.5 text-sm font-extrabold text-white shadow-cta"
        >
          {t('loginCta')}
        </button>
      </div>
    </BottomSheet>
  );
}
