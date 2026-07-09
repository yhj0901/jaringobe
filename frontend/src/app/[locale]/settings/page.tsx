import type { Metadata } from 'next';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import { SettingsController } from '@/features/settings/SettingsController';

interface SettingsPageProps {
  params: { locale: string };
}

export async function generateMetadata({
  params: { locale },
}: SettingsPageProps): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: 'metadata' });
  return {
    title: t('settings.title'),
    description: t('settings.description'),
  };
}

/**
 * 설정 (`/settings`) — 보호 라우트 (미들웨어 PROTECTED_PATHS, ui-design 9장).
 * 계정 / 내 식생활 설정(단일 편집 → 재생성 확인) / 자동 주문 연동 스토어 (FR-401~404).
 */
export default function SettingsPage({ params: { locale } }: SettingsPageProps) {
  setRequestLocale(locale);
  return <SettingsController />;
}
