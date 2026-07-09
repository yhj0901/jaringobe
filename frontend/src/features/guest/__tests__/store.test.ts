import { beforeEach, describe, expect, it } from 'vitest';
import { useGuestStore, type GuestPlan } from '@/features/guest/store';
import {
  GUEST_SCHEMA_VERSION,
  GUEST_STORAGE_KEY,
  GUEST_TTL_MS,
} from '@/shared/config/constants';

const SAMPLE_PLAN: GuestPlan = {
  householdSize: 4,
  amount: '700000',
  currency: 'KRW',
  mealDirection: 'kids',
};

function resetStore() {
  useGuestStore.setState({ plan: undefined, promptHistory: {}, savedAt: undefined });
  window.localStorage.clear();
}

function writePersisted(savedAt: string) {
  window.localStorage.setItem(
    GUEST_STORAGE_KEY,
    JSON.stringify({
      state: { plan: SAMPLE_PLAN, promptHistory: {}, savedAt },
      version: GUEST_SCHEMA_VERSION,
    }),
  );
}

describe('게스트 스토어 (FR-107)', () => {
  beforeEach(resetStore);

  it('setPlan 이 savedAt 과 함께 localStorage 에 버전 필드로 저장한다', () => {
    useGuestStore.getState().setPlan(SAMPLE_PLAN);
    const raw = window.localStorage.getItem(GUEST_STORAGE_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string) as {
      state: { plan: GuestPlan; savedAt: string };
      version: number;
    };
    expect(parsed.version).toBe(GUEST_SCHEMA_VERSION);
    expect(parsed.state.plan).toEqual(SAMPLE_PLAN);
    expect(Date.parse(parsed.state.savedAt)).not.toBeNaN();
  });

  it('30일 이내 데이터는 rehydrate 로 복원된다', async () => {
    writePersisted(new Date(Date.now() - GUEST_TTL_MS + 60_000).toISOString());
    await useGuestStore.persist.rehydrate();
    expect(useGuestStore.getState().plan).toEqual(SAMPLE_PLAN);
  });

  it('30일이 지난 데이터는 복원하지 않고 localStorage 에서 제거한다', async () => {
    writePersisted(new Date(Date.now() - GUEST_TTL_MS - 60_000).toISOString());
    await useGuestStore.persist.rehydrate();
    expect(useGuestStore.getState().plan).toBeUndefined();
    expect(window.localStorage.getItem(GUEST_STORAGE_KEY)).toBeNull();
  });

  it('savedAt 이 손상된 항목은 복원하지 않는다', async () => {
    writePersisted('not-a-date');
    await useGuestStore.persist.rehydrate();
    expect(useGuestStore.getState().plan).toBeUndefined();
  });

  it('JSON 이 손상된 항목은 제거하고 무시한다', async () => {
    window.localStorage.setItem(GUEST_STORAGE_KEY, '{broken json');
    await useGuestStore.persist.rehydrate();
    expect(useGuestStore.getState().plan).toBeUndefined();
    expect(window.localStorage.getItem(GUEST_STORAGE_KEY)).toBeNull();
  });

  it('clearGuestData 가 예산안·이력을 모두 초기화한다', () => {
    useGuestStore.getState().setPlan(SAMPLE_PLAN);
    useGuestStore.getState().markAutoOrderNotified();
    useGuestStore.getState().clearGuestData();
    const state = useGuestStore.getState();
    expect(state.plan).toBeUndefined();
    expect(state.promptHistory).toEqual({});
    expect(state.savedAt).toBeUndefined();
  });

  it('markAutoOrderNotified 가 promptHistory 에 시각을 기록한다 (FR-106)', () => {
    useGuestStore.getState().markAutoOrderNotified();
    const at = useGuestStore.getState().promptHistory.autoOrderNotifiedAt;
    expect(at).toBeDefined();
    expect(Date.parse(at as string)).not.toBeNaN();
  });

  it('PII/토큰 없이 비식별 데이터만 저장한다 (CWE-922)', () => {
    useGuestStore.getState().setPlan(SAMPLE_PLAN);
    const parsed = JSON.parse(window.localStorage.getItem(GUEST_STORAGE_KEY) as string) as {
      state: Record<string, unknown>;
    };
    expect(Object.keys(parsed.state).sort()).toEqual(['plan', 'promptHistory', 'savedAt']);
  });
});
