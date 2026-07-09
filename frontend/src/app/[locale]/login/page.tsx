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
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-8 px-6 py-10">
      <header className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-3xl font-extrabold text-brand-700">{t('auth.login.title')}</h1>
        <p className="text-sm font-medium tracking-wide text-gray-500">{t('auth.login.slogan')}</p>
      </header>

      {errorKey !== null ? (
        <div role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          <p>{t(errorKey)}</p>
          <p className="mt-1 text-xs text-red-500">{t('auth.login.retryHint')}</p>
        </div>
      ) : null}

      {noticeKey !== null ? (
        <p role="status" className="rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">
          {t(noticeKey)}
        </p>
      ) : null}

      <SocialLoginButtons next={next} />

      <p className="text-center text-xs text-gray-400">{t('auth.login.terms')}</p>
    </main>
  );
}
