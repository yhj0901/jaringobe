import type { StoreId } from '@/features/store/types';
import type { Country } from '@/shared/api/types';

/**
 * 스토어 연동 상수 — 프로토타입 STORE_META 와 동일 브랜드 스타일 (ui-design 9·12장).
 * 이름·모노그램은 로캘별 표기가 달라 i18n 키(`store.{id}.name` / `store.{id}.mono`)로 관리.
 */

/** 국가별 스토어 노출 순서 (api-spec §6, FR-603) — KR 4종 / US 2종 */
export const STORE_IDS_BY_COUNTRY: Record<Country, readonly StoreId[]> = {
  KR: ['kurly', 'coupang', 'ssg', 'naver'],
  US: ['walmart', 'instacart'],
};

/** country 의 스토어 세트 — 미정의 국가는 KR 폴백 (백엔드 stores_for_country 와 정합) */
export function storeIdsForCountry(country: string): readonly StoreId[] {
  return STORE_IDS_BY_COUNTRY[country as Country] ?? STORE_IDS_BY_COUNTRY.KR;
}

/** KR 기본 노출 세트 (하위 호환 — 기존 참조 유지) */
export const STORE_IDS: readonly StoreId[] = STORE_IDS_BY_COUNTRY.KR;

/**
 * 브랜드 배지/버튼 색 (프로토타입 STORE_META.c).
 * KR: 컬리 퍼플/쿠팡 블루/SSG 레드/네이버 그린 · US: Walmart #0071CE / Instacart #43B02A (ui-design 12장).
 */
export const STORE_BRAND_COLORS: Record<StoreId, string> = {
  kurly: '#5F0080',
  coupang: '#2D6FF7',
  ssg: '#F23C2E',
  naver: '#03C75A',
  walmart: '#0071CE',
  instacart: '#43B02A',
};
