'use client';

import { useLocale, useTranslations } from 'next-intl';
import {
  buildAuthorizeUrl,
  providerOrder,
  type SocialProvider,
} from '@/features/auth/authorizeUrl';

interface SocialLoginButtonsProps {
  next?: string;
}

const PROVIDER_CLASS: Record<SocialProvider, string> = {
  kakao: 'bg-[#FEE500] text-[#191919]',
  google: 'border border-gray-300 bg-white text-gray-800',
  apple: 'bg-black text-white',
};

/** 소셜 로그인 버튼 목록 — 로캘별 순서, 브랜드 가이드 기반 스타일 (FR-001/007) */
export function SocialLoginButtons({ next }: SocialLoginButtonsProps) {
  const locale = useLocale();
  const t = useTranslations('auth.login');

  const handleClick = (provider: SocialProvider) => {
    // OAuth 는 브라우저 내비게이션 전용 (api-spec 1-1) — fetch 아님
    window.location.href = buildAuthorizeUrl(provider, next);
  };

  return (
    <div className="flex w-full flex-col gap-3">
      {providerOrder(locale).map((provider) => (
        <button
          key={provider}
          type="button"
          onClick={() => handleClick(provider)}
          className={`w-full rounded-xl px-4 py-3.5 text-sm font-bold ${PROVIDER_CLASS[provider]}`}
        >
          {t(provider)}
        </button>
      ))}
      {/*
        애플 로그인 (P1) — iOS 앱 출시 전 필수 (docs/기획/로그인-소셜인증.md FR-009).
        어댑터 인터페이스는 3사 공통으로 확정되어 있어 아래 한 줄로 활성화한다:
        providerOrder() 의 P1 주석 순서 적용 + auth.login.apple 키는 이미 준비됨.
      */}
    </div>
  );
}
