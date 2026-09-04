import { storeIdsForCountry } from '@/features/store/constants';
import type { StoreConnection, StoreId } from '@/features/store/types';

/**
 * user.country 스토어 세트 순서에서 첫 connected 스토어 (POST /orders body.store).
 * 응답 배열 순서가 달라도 국가 세트 순서를 따른다.
 */
export function pickFirstConnectedStore(
  country: string,
  connections: readonly StoreConnection[],
): StoreId | null {
  const connected = new Set(
    connections.filter((item) => item.status === 'connected').map((item) => item.store),
  );
  for (const id of storeIdsForCountry(country)) {
    if (connected.has(id)) return id;
  }
  return null;
}
