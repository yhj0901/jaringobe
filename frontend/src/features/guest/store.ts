import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';
import {
  GUEST_SCHEMA_VERSION,
  GUEST_STORAGE_KEY,
  GUEST_TTL_MS,
} from '@/shared/config/constants';
import type { MealDirection, Money } from '@/shared/api/types';

/**
 * 게스트 상태 (FR-107) — localStorage 30일 보관, PII/토큰 저장 금지 (CWE-922).
 * 보관 항목: 예산안(인원·금액·통화·식단 방향) + 프롬프트 노출 이력 + savedAt.
 */

export interface GuestPlan {
  householdSize: number;
  amount: string;
  currency: Money['currency'];
  mealDirection: MealDirection;
}

interface GuestStateData {
  plan?: GuestPlan;
  promptHistory: {
    /** 자동주문 알림 1회 노출 기록 (FR-106) */
    autoOrderNotifiedAt?: string;
  };
  savedAt?: string;
}

interface GuestState extends GuestStateData {
  setPlan: (plan: GuestPlan) => void;
  clearGuestData: () => void;
  markAutoOrderNotified: () => void;
}

const INITIAL_DATA: GuestStateData = {
  plan: undefined,
  promptHistory: {},
  savedAt: undefined,
};

/** savedAt 기준 30일 만료를 검사하는 localStorage 래퍼 (FR-107) */
export const expiringLocalStorage: StateStorage = {
  getItem: (name) => {
    if (typeof window === 'undefined') return null;
    const raw = window.localStorage.getItem(name);
    if (raw === null) return null;
    try {
      const parsed: unknown = JSON.parse(raw);
      const savedAt = (parsed as { state?: { savedAt?: unknown } })?.state?.savedAt;
      if (typeof savedAt === 'string') {
        const savedTime = Date.parse(savedAt);
        if (Number.isNaN(savedTime) || Date.now() - savedTime > GUEST_TTL_MS) {
          window.localStorage.removeItem(name);
          return null;
        }
      }
    } catch {
      window.localStorage.removeItem(name);
      return null;
    }
    return raw;
  },
  setItem: (name, value) => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(name, value);
  },
  removeItem: (name) => {
    if (typeof window === 'undefined') return;
    window.localStorage.removeItem(name);
  },
};

export const useGuestStore = create<GuestState>()(
  persist(
    (set) => ({
      ...INITIAL_DATA,
      setPlan: (plan) =>
        set({
          plan,
          savedAt: new Date().toISOString(),
        }),
      clearGuestData: () => set({ ...INITIAL_DATA }),
      markAutoOrderNotified: () =>
        set((state) => ({
          promptHistory: {
            ...state.promptHistory,
            autoOrderNotifiedAt: new Date().toISOString(),
          },
        })),
    }),
    {
      name: GUEST_STORAGE_KEY,
      version: GUEST_SCHEMA_VERSION,
      storage: createJSONStorage(() => expiringLocalStorage),
      // SSR 하이드레이션 불일치 방지 — 클라이언트 마운트 후 수동 rehydrate
      skipHydration: true,
      partialize: (state) => ({
        plan: state.plan,
        promptHistory: state.promptHistory,
        savedAt: state.savedAt,
      }),
    },
  ),
);
