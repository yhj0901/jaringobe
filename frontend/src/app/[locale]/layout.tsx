import type { Metadata, Viewport } from 'next';
import { notFound } from 'next/navigation';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getTranslations, setRequestLocale } from 'next-intl/server';
import { routing, isAppLocale } from '@/i18n/routing';
import '@/app/globals.css';

interface LocaleLayoutProps {
  children: React.ReactNode;
  params: { locale: string };
}

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

/** PWA — 상태바/테마 컬러(브랜드 네이비) + 모바일 뷰포트 */
export const viewport: Viewport = {
  themeColor: '#0B1B3A',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

/** SEO/OG 메타 — 로캘별 title/description + hreflang (FR-110) */
export async function generateMetadata({
  params: { locale },
}: Omit<LocaleLayoutProps, 'children'>): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: 'metadata' });
  return {
    metadataBase: new URL('https://jaringobe.cloud'),
    title: t('home.title'),
    description: t('home.description'),
    openGraph: {
      title: t('home.title'),
      description: t('home.description'),
      locale: locale === 'ko' ? 'ko_KR' : 'en_US',
      type: 'website',
      images: [
        {
          url: '/opengraph-image.png',
          width: 800,
          height: 800,
          alt: 'Jaringobe',
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title: t('home.title'),
      description: t('home.description'),
      images: ['/twitter-image.png'],
    },
    manifest: '/manifest.webmanifest',
    appleWebApp: {
      capable: true,
      statusBarStyle: 'default',
      title: '자린고비',
    },
    icons: {
      icon: '/icon-192.png',
      shortcut: '/icon-192.png',
      apple: '/apple-icon.png',
    },
    alternates: {
      languages: {
        ko: '/ko',
        en: '/en',
        'x-default': '/ko',
      },
    },
  };
}

export default async function LocaleLayout({ children, params: { locale } }: LocaleLayoutProps) {
  if (!isAppLocale(locale)) {
    notFound();
  }
  setRequestLocale(locale);
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider messages={messages}>{children}</NextIntlClientProvider>
      </body>
    </html>
  );
}
