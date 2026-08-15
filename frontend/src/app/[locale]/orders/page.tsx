import type { Metadata } from 'next';
import { getTranslations, setRequestLocale } from 'next-intl/server';
import { OrdersController } from '@/features/order/OrdersController';

interface OrdersPageProps {
  params: { locale: string };
}

export async function generateMetadata({
  params: { locale },
}: OrdersPageProps): Promise<Metadata> {
  const t = await getTranslations({ locale, namespace: 'metadata' });
  return {
    title: t('orders.title'),
    description: t('orders.description'),
  };
}

/**
 * 장바구니 리뷰 (`/orders`) — 보호 라우트 (미들웨어 PROTECTED_PATHS, ui-design 13장).
 * 미인증 시 `/login?next=/orders`.
 */
export default function OrdersPage({ params: { locale } }: OrdersPageProps) {
  setRequestLocale(locale);
  return <OrdersController />;
}
