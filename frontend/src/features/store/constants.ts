import type { StoreId } from '@/features/store/types';

/**
 * 스토어 연동 상수 — 프로토타입 STORE_META(KR 4종)와 동일 브랜드 스타일 (ui-design 9장).
 * 이름·모노그램은 로캘별 표기가 달라 i18n 키(`store.{id}.name` / `store.{id}.mono`)로 관리.
 */

/** KR 스토어 노출 순서 (프로토타입 STORES_KR) */
export const STORE_IDS: readonly StoreId[] = ['kurly', 'coupang', 'ssg', 'naver'];

/** 브랜드 배지/버튼 색 (프로토타입 STORE_META.c — 컬리 퍼플/쿠팡 블루/SSG 레드/네이버 그린) */
export const STORE_BRAND_COLORS: Record<StoreId, string> = {
  kurly: '#5F0080',
  coupang: '#2D6FF7',
  ssg: '#F23C2E',
  naver: '#03C75A',
};
