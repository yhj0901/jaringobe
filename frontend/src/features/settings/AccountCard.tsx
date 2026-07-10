'use client';

import { useTranslations } from 'next-intl';

interface AccountCardProps {
  nickname: string;
  email: string | null;
  onLogout: () => void;
}

/**
 * 계정 카드 (FR-401, 프로토타입 settings account 재현)
 * GB 아바타 + 닉네임·이메일 + "로그인됨" 배지 + 로그아웃 버튼(확인 시트는 호출측).
 */
export function AccountCard({ nickname, email, onLogout }: AccountCardProps) {
  const t = useTranslations('settings.account');

  return (
    <section aria-label={t('section')}>
      <h2 className="mx-0.5 mb-2 text-xs font-extrabold tracking-wide text-ink-400">
        {t('section')}
      </h2>
      <div className="rounded-[18px] bg-white shadow-card">
        <div className="flex items-center gap-[13px] p-4">
          <img
            src="/icon.png"
            alt="Jaringobe"
            aria-hidden
            className="h-12 w-12 shrink-0 rounded-[14px] object-cover"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-extrabold text-navy-900">{nickname}</p>
            <p className="truncate text-[12.5px] text-ink-400">{email ?? t('noEmail')}</p>
          </div>
          <span className="shrink-0 rounded-full bg-mint-50 px-2.5 py-1 text-[11px] font-extrabold text-mint-600">
            {t('loggedIn')}
          </span>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="w-full border-t border-[#F1F3F8] py-3.5 text-center text-sm font-bold text-[#C2453A]"
        >
          {t('logout')}
        </button>
      </div>
    </section>
  );
}
