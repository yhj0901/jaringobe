import type { Metadata } from 'next';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import { NotificationSettingsController } from '@/features/notification/NotificationSettingsController';

interface NotificationSettingsPageProps {
  params: { locale: string };
}

export async function generateMetadata({
  params: { locale },
}: NotificationSettingsPageProps): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: 'metadata' });
  return {
    title: t('notifications.title'),
    description: t('notifications.description'),
  };
}

/**
 * 알림 설정 (`/settings/notifications`) — 보호 라우트 (미들웨어 `/settings` prefix, ui-design 12장).
 * 식단 완성 토글 / 식사 리마인더 3행 / 웹 안내 카드 / OS 권한 거부 배너 (FR-007).
 */
export default function NotificationSettingsPage({
  params: { locale },
}: NotificationSettingsPageProps) {
  setRequestLocale(locale);
  return <NotificationSettingsController />;
}
