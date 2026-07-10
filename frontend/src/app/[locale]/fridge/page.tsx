import { setRequestLocale } from 'next-intl/server';
import { FridgeManager } from '@/features/fridge/FridgeManager';

interface FridgePageProps {
  params: { locale: string };
}

/**
 * 가상 냉장고 (`/fridge`) — 수동 재고 관리 (목록/추가/삭제).
 * 백엔드 fridge API 연동. 배송 자동등록·식사완료 자동차감은 후속.
 */
export default function FridgePage({ params: { locale } }: FridgePageProps) {
  setRequestLocale(locale);
  return <FridgeManager />;
}
