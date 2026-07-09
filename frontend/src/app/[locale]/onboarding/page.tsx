import { getTranslations, setRequestLocale } from 'next-intl/server';
import { Link } from '@/i18n/routing';

interface OnboardingPageProps {
  params: { locale: string };
  searchParams: { imported?: string };
}

/**
 * 온보딩 (`/onboarding`) — 라우트 예약 (본 구현은 household 기획).
 * 이번 범위: 게스트 예산안 이전 성공 확인 화면 1장 (?imported=1, FR-108) + 스텁.
 */
export default async function OnboardingPage({
  params: { locale },
  searchParams,
}: OnboardingPageProps) {
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: 'onboarding' });
  const imported = searchParams.imported === '1';

  if (imported) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-xl font-bold text-gray-900">{t('imported.title')}</h1>
        <p className="text-sm text-gray-600">{t('imported.description')}</p>
        <Link
          href="/"
          className="mt-2 w-full rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
        >
          {t('imported.homeCta')}
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-xl font-bold text-gray-900">{t('title')}</h1>
      <p className="text-sm text-gray-600">{t('stub')}</p>
      <Link
        href="/"
        className="mt-2 w-full rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white"
      >
        {t('stubHomeCta')}
      </Link>
    </main>
  );
}
