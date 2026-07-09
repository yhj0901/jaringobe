import type { Metadata } from 'next';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import { SocialLoginButtons } from '@/features/auth/SocialLoginButtons';
import { sanitizeNextPath } from '@/features/auth/authorizeUrl';
import { KNOWN_ERROR_CODES, KNOWN_NOTICE_CODES } from '@/shared/config/constants';

interface LoginPageProps {
  params: { locale: string };
  searchParams: { error?: string; notice?: string; next?: string };
}

export async function generateMetadata({
  params: { locale },
}: Pick<LoginPageProps, 'params'>): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: 'metadata' });
  return {
    title: t('login.title'),
    description: t('login.description'),
  };
}

/**
 * 로그인 페이지 (`/login`) — RSC (ui-design 1/5장).
 * Claude Design 프로토타입의 네이비 그라디언트 로그인 화면 재현:
 * 상단 브랜드(GB 타일 + 워드마크) → 태그라인/슬로건 → 하단 소셜 버튼 + 약관.
 * ?error / ?notice 쿼리를 i18n 배너로 표시 (detail.code → auth.error.{code} 규약).
 */
export default async function LoginPage({ params: { locale }, searchParams }: LoginPageProps) {
  setRequestLocale(locale);
  const t = await getTranslations({ locale });

  const { error, notice } = searchParams;
  const next = sanitizeNextPath(searchParams.next);

  const errorKey =
    error !== undefined
      ? (KNOWN_ERROR_CODES as readonly string[]).includes(error)
        ? `auth.error.${error}`
        : 'common.error.fallback'
      : null;

  const noticeKey =
    notice !== undefined && (KNOWN_NOTICE_CODES as readonly string[]).includes(notice)
      ? `auth.notice.${notice}`
      : null;

  return (
    <main className="flex min-h-screen items-stretch justify-center sm:items-center sm:px-6 sm:py-10">
      {/* 모바일: 풀스크린 / 데스크톱: ~480px 앱 프레임 */}
      <div className="flex min-h-screen w-full max-w-[480px] flex-col bg-[linear-gradient(165deg,#1C2E58_0%,#0B1B3A_100%)] px-7 pb-9 pt-12 text-white sm:min-h-[760px] sm:rounded-[32px] sm:shadow-hero">
        <header className="flex flex-1 flex-col justify-center">
          <div className="mb-6 flex items-center gap-2.5">
            <span
              aria-hidden
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-white text-[13px] font-extrabold text-navy-900"
            >
              GB
            </span>
            <h1 className="text-lg font-extrabold tracking-tight" aria-label={t('auth.login.title')}>
              <span aria-hidden>
                JARIN<span className="text-brand-400">GO BE</span>
              </span>
            </h1>
          </div>
          <p className="mb-2 text-[13px] font-bold text-brand-400">{t('auth.login.tag')}</p>
          <p className="whitespace-pre-line text-3xl font-extrabold leading-[1.3] tracking-tight">
            {t('auth.login.subtitle')}
          </p>
        </header>

        <div className="flex flex-col gap-2.5">
          {errorKey !== null ? (
            <div role="alert" className="rounded-2xl bg-white/95 px-4 py-3 text-sm text-red-700">
              <p>{t(errorKey)}</p>
              <p className="mt-1 text-xs text-red-500">{t('auth.login.retryHint')}</p>
            </div>
          ) : null}

          {noticeKey !== null ? (
            <p role="status" className="rounded-2xl bg-white/95 px-4 py-3 text-sm text-blue-800">
              {t(noticeKey)}
            </p>
          ) : null}

          <SocialLoginButtons next={next} />

          <p className="mt-2 text-center text-[11px] leading-relaxed text-white/50">
            {t('auth.login.terms')}
          </p>
        </div>
      </div>
    </main>
  );
}
