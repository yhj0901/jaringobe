'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { fetchOrderPreview } from '@/features/order/api';
import { RECOMMENDED_CHIP_CAP } from '@/features/order/types';
import { fetchStoreConnections } from '@/features/store/api';
import type { StoreBadge } from '@/features/home/types';

export interface MemberAutoOrderState {
  active: boolean;
  stores: StoreBadge[];
  recommendedItems: string[];
  moreCount: number;
  loading: boolean;
}

const INITIAL: MemberAutoOrderState = {
  active: false,
  stores: [],
  recommendedItems: [],
  moreCount: 0,
  loading: true,
};

/**
 * 회원 홈 자동주문 카드 데이터 — GET /stores/connections + GET /orders/preview.
 * 연동 0개 → 비활성. 연동 1개+ → 활성 + needed 이름 칩 (최대 N, 초과 +K).
 */
export function useMemberAutoOrder(): MemberAutoOrderState {
  const tStore = useTranslations('store');
  const [state, setState] = useState<MemberAutoOrderState>(INITIAL);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [storesRes, previewRes] = await Promise.all([
        fetchStoreConnections(),
        fetchOrderPreview(),
      ]);
      if (cancelled) return;

      const connected = storesRes.ok
        ? storesRes.data.connections.filter((item) => item.status === 'connected')
        : [];
      const stores: StoreBadge[] = connected.map((item) => ({
        id: item.store,
        name: tStore(`${item.store}.name`),
      }));

      const names = previewRes.ok ? previewRes.data.needed.map((line) => line.name) : [];
      const recommendedItems = names.slice(0, RECOMMENDED_CHIP_CAP);
      const moreCount = Math.max(0, names.length - RECOMMENDED_CHIP_CAP);

      setState({
        active: connected.length > 0,
        stores,
        recommendedItems,
        moreCount,
        loading: false,
      });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [tStore]);

  return state;
}
