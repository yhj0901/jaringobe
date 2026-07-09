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
      <h2 id="signup-gate-title" className="mb-2 text-base font-bold text-gray-900">
        {t('title')}
      </h2>
      <p className="mb-4 text-sm text-gray-600">{t('description')}</p>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 rounded-xl border border-gray-300 px-4 py-3 text-sm font-medium text-gray-700"
        >
          {t('later')}
        </button>
        <button
          type="button"
          onClick={onLogin}
          className="flex-1 rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
        >
          {t('loginCta')}
        </button>
      </div>
    </BottomSheet>
  );
}
