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

/** 브랜드 버튼 스타일 — Claude Design 프로토타입 로그인 화면 기준 */
const PROVIDER_CLASS: Record<SocialProvider, string> = {
  kakao: 'bg-kakao text-[#191600]',
  google: 'bg-white text-[#1F1F1F]',
  apple: 'bg-black text-white',
};

/** 브랜드 아이콘 — 디자인 마크업의 인라인 SVG 재사용 */
const PROVIDER_ICON: Record<SocialProvider, JSX.Element> = {
  kakao: (
    <svg aria-hidden width="19" height="19" viewBox="0 0 24 24" fill="none">
      <ellipse cx="12" cy="10.5" rx="9" ry="7.2" fill="#191600" />
      <path d="M7 16.5l-1 4 4.2-2.6" fill="#191600" />
    </svg>
  ),
  google: (
    <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path
        d="M21.6 12.2c0-.6-.05-1.2-.16-1.8H12v3.4h5.4a4.6 4.6 0 0 1-2 3v2.5h3.2c1.9-1.7 3-4.3 3-7.1z"
        fill="#4285F4"
      />
      <path
        d="M12 22c2.7 0 5-.9 6.6-2.4l-3.2-2.5c-.9.6-2 .9-3.4.9-2.6 0-4.8-1.7-5.6-4.1H3.1v2.6A10 10 0 0 0 12 22z"
        fill="#34A853"
      />
      <path d="M6.4 13.9a6 6 0 0 1 0-3.8V7.5H3.1a10 10 0 0 0 0 9z" fill="#FBBC05" />
      <path
        d="M12 6c1.5 0 2.8.5 3.8 1.5l2.8-2.8A10 10 0 0 0 3.1 7.5l3.3 2.6C7.2 7.7 9.4 6 12 6z"
        fill="#EA4335"
      />
    </svg>
  ),
  apple: (
    <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="#fff">
      <path d="M16.4 12.7c0-2.2 1.8-3.3 1.9-3.4-1-1.5-2.6-1.7-3.2-1.7-1.4-.1-2.7.8-3.4.8-.7 0-1.8-.8-2.9-.8-1.5 0-2.9.9-3.6 2.2-1.6 2.7-.4 6.7 1.1 8.9.7 1.1 1.6 2.3 2.7 2.2 1.1 0 1.5-.7 2.8-.7 1.3 0 1.7.7 2.8.7 1.2 0 1.9-1.1 2.6-2.1.8-1.2 1.2-2.4 1.2-2.4s-2.3-.9-2.3-3.6z" />
      <path d="M14.3 6c.6-.7 1-1.7.9-2.7-.9 0-1.9.6-2.5 1.3-.6.6-1 1.6-.9 2.6 1 .1 1.9-.5 2.5-1.2z" />
    </svg>
  ),
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
    <div className="flex w-full flex-col gap-2.5">
      {providerOrder(locale).map((provider) => (
        <button
          key={provider}
          type="button"
          onClick={() => handleClick(provider)}
          className={`flex w-full items-center justify-center gap-2 rounded-[14px] px-4 py-4 text-[15px] font-extrabold ${PROVIDER_CLASS[provider]}`}
        >
          {PROVIDER_ICON[provider]}
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
