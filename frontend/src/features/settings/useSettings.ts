'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { fetchMe } from '@/features/auth/useSession';
import { postLogout } from '@/features/auth/logout';
import {
  fetchBudgetPlan,
  fetchHousehold,
  putBudgetPlan,
  putHouseholdMembers,
} from '@/features/household/api';
import { budgetRange } from '@/features/household/onboardingLogic';
import { createMealPlan, fetchLatestMealPlan, regenerateMealPlan } from '@/features/mealplan/api';
import {
  MEALPLAN_DAYS_DEFAULT,
  MEALPLAN_MEALS_PER_DAY,
  MEALPLAN_NOT_FOUND_CODE,
} from '@/features/mealplan/constants';
import { fetchStoreConnections, putStoreConnection } from '@/features/store/api';
import { STORE_IDS } from '@/features/store/constants';
import { VISITED_MARKER_KEY } from '@/shared/config/constants';
import type { Cuisine, HouseholdMemberInput } from '@/features/household/types';
import type { StoreId } from '@/features/store/types';
import type { MealDirection, Money, UserMeResponse } from '@/shared/api/types';

/**
 * 설정 페이지 데이터 어댑터 (ui-design 9장, FR-401~404)
 * users/me + households/me + budget/plans(현재값, api-spec 2-2 v1.3.1)
 * + mealplans/latest(재생성 대상) + stores/connections.
 */

export type SettingsStatus = 'loading' | 'unauthenticated' | 'error' | 'ready';
export type DietSection = 'household' | 'budget' | 'preference';
export type RegenerateOutcome = 'ok' | 'rate-limited' | 'failed';

/**
 * 식생활 프로필 (방향·선호·락) — GET /budget/plans(api-spec 2-2) 현재값으로 확정(known).
 * 404(예산안 없음)면 미확정 — 요약은 기존 폴백("설정됨") 유지, 부분 저장 병합 베이스는 기본값.
 */
export interface DietProfile {
  direction: MealDirection;
  cuisines: Cuisine[];
  locked: boolean;
  known: boolean;
}

const INITIAL_PROFILE: DietProfile = {
  direction: 'health',
  cuisines: [],
  locked: true,
  known: false,
};

/** household 미설정(404) 시 예산 upsert 의 householdSize 폴백 (온보딩 기본 프리셋과 동일) */
const FALLBACK_HOUSEHOLD_SIZE = 2;

export interface SettingsState {
  status: SettingsStatus;
  user: UserMeResponse | null;
  /** GET households/me — 404 HOUSEHOLD_NOT_FOUND 면 null (설정 전) */
  members: HouseholdMemberInput[] | null;
  /** 예산 현재값 — GET budget/plans 우선, 404 면 mealplans/latest 요약 폴백 (없으면 null) */
  budget: Money | null;
  /** 최신 식단 id — 재생성 대상 (없으면 생성 폴백, FR-403) */
  planId: string | null;
  connections: Record<StoreId, boolean> | null;
  profile: DietProfile;
  saving: boolean;
  togglingStore: StoreId | null;
  generating: boolean;
  loggingOut: boolean;
  saveHousehold: (members: HouseholdMemberInput[]) => Promise<boolean>;
  saveBudget: (amount: string, locked: boolean) => Promise<boolean>;
  savePreference: (cuisines: Cuisine[], direction: MealDirection) => Promise<boolean>;
  toggleStore: (store: StoreId, connected: boolean) => Promise<boolean>;
  regenerate: () => Promise<RegenerateOutcome>;
  /** 성공 시 visited 마커 기록까지 수행 — 홈 이동은 호출측 (FR-401) */
  logout: () => Promise<boolean>;
  reload: () => void;
}

export function useSettings(): SettingsState {
  const tCuisine = useTranslations('cuisine');

  const [status, setStatus] = useState<SettingsStatus>('loading');
  const [user, setUser] = useState<UserMeResponse | null>(null);
  const [members, setMembers] = useState<HouseholdMemberInput[] | null>(null);
  const [budget, setBudget] = useState<Money | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [connections, setConnections] = useState<Record<StoreId, boolean> | null>(null);
  const [profile, setProfile] = useState<DietProfile>(INITIAL_PROFILE);
  const [saving, setSaving] = useState(false);
  const [togglingStore, setTogglingStore] = useState<StoreId | null>(null);
  const [generating, setGenerating] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const membersRef = useRef<HouseholdMemberInput[] | null>(null);
  const profileRef = useRef<DietProfile>(INITIAL_PROFILE);
  const planIdRef = useRef<string | null>(null);

  const applyMembers = useCallback((next: HouseholdMemberInput[] | null) => {
    membersRef.current = next;
    setMembers(next);
  }, []);

  const applyProfile = useCallback((next: DietProfile) => {
    profileRef.current = next;
    setProfile(next);
  }, []);

  const load = useCallback(async () => {
    setStatus('loading');
    const me = await fetchMe();
    if (!me.ok) {
      setStatus(me.status === 401 ? 'unauthenticated' : 'error');
      return;
    }
    setUser(me.data);

    const [household, budgetPlan, latest, stores] = await Promise.all([
      fetchHousehold(),
      fetchBudgetPlan(),
      fetchLatestMealPlan(),
      fetchStoreConnections(),
    ]);

    if (household.ok) {
      applyMembers(household.data.members);
    } else if (household.status === 404) {
      applyMembers(null); // HOUSEHOLD_NOT_FOUND — 온보딩 전 (설정 전 표기)
    } else {
      setStatus('error');
      return;
    }

    // 예산안 현재값 (api-spec 2-2) — 요약·편집 초기값·부분 수정 병합 베이스 (FR-402)
    let budgetKnown = false;
    if (budgetPlan.ok) {
      budgetKnown = true;
      setBudget(budgetPlan.data.budget);
      applyProfile({
        direction: budgetPlan.data.mealDirection,
        cuisines: budgetPlan.data.cuisines,
        locked: budgetPlan.data.locked,
        known: true,
      });
    } else if (budgetPlan.status === 404) {
      applyProfile(INITIAL_PROFILE); // BUDGET_PLAN_NOT_FOUND — 기존 폴백 유지 (reload 시 초기화)
    } else {
      setStatus('error');
      return;
    }

    if (latest.ok) {
      planIdRef.current = latest.data.id;
      setPlanId(latest.data.id);
      if (!budgetKnown) setBudget(latest.data.budgetSummary.budget);
    } else if (latest.status === 404 && latest.code === MEALPLAN_NOT_FOUND_CODE) {
      planIdRef.current = null;
      setPlanId(null);
      if (!budgetKnown) setBudget(null);
    } else {
      setStatus('error');
      return;
    }

    if (!stores.ok) {
      setStatus('error');
      return;
    }
    const map = Object.fromEntries(
      STORE_IDS.map((id) => [
        id,
        stores.data.connections.some(
          (connection) => connection.store === id && connection.status === 'connected',
        ),
      ]),
    ) as Record<StoreId, boolean>;
    setConnections(map);

    setStatus('ready');
  }, [applyMembers, applyProfile]);

  useEffect(() => {
    void load();
  }, [load]);

  /** FR-402: 가구 구성 저장 — PUT households/me (전체 교체) */
  const saveHousehold = useCallback(
    async (nextMembers: HouseholdMemberInput[]) => {
      setSaving(true);
      const result = await putHouseholdMembers(nextMembers);
      setSaving(false);
      if (!result.ok) return false;
      applyMembers(result.data.members);
      return true;
    },
    [applyMembers],
  );

  /**
   * FR-402: 예산·선호 저장 — PUT budget/plans (upsert).
   * 병합 베이스는 GET /budget/plans 로 확정된 서버 현재값(profileRef) — 예산만 수정해도
   * 서버의 mealDirection/cuisines/locked 이 보존된다 (api-spec 2-2 v1.3.1).
   */
  const upsertBudgetPlan = useCallback(
    async (next: DietProfile, amount: string | null) => {
      const currentUser = user;
      const currency: Money['currency'] = currentUser?.currency === 'USD' ? 'USD' : 'KRW';
      const size = membersRef.current?.length ?? FALLBACK_HOUSEHOLD_SIZE;
      // 예산 현재값 미확인(404) 상태에서 선호만 저장하는 경우 — 권장값 폴백 (검증 범위 준수, CWE-20)
      const money: Money =
        amount !== null
          ? { amount, currency }
          : budget ?? { amount: String(budgetRange(size, currency).rec), currency };
      setSaving(true);
      const result = await putBudgetPlan({
        householdSize: size,
        budget: money,
        mealDirection: next.direction,
        locked: next.locked,
        cuisines: next.cuisines,
      });
      setSaving(false);
      if (!result.ok) return false;
      setBudget(result.data.budget);
      applyProfile(next);
      return true;
    },
    [user, budget, applyProfile],
  );

  const saveBudget = useCallback(
    (amount: string, locked: boolean) =>
      upsertBudgetPlan({ ...profileRef.current, locked }, amount),
    [upsertBudgetPlan],
  );

  const savePreference = useCallback(
    (cuisines: Cuisine[], direction: MealDirection) =>
      upsertBudgetPlan({ ...profileRef.current, cuisines, direction, known: true }, null),
    [upsertBudgetPlan],
  );

  /** FR-404: 연동 표시 저장/해제 — PUT stores/connections/{store} */
  const toggleStore = useCallback(
    async (store: StoreId, connected: boolean) => {
      setTogglingStore(store);
      const result = await putStoreConnection(store, connected);
      setTogglingStore(null);
      if (!result.ok) return false;
      setConnections((current) => (current === null ? current : { ...current, [store]: connected }));
      return true;
    },
    [],
  );

  /** FR-403: 저장 후 재생성 — latest 있으면 regenerate, 없으면 생성 폴백 */
  const regenerate = useCallback(async (): Promise<RegenerateOutcome> => {
    setGenerating(true);
    const currentPlanId = planIdRef.current;
    const result =
      currentPlanId !== null
        ? await regenerateMealPlan(currentPlanId)
        : await createMealPlan({
            days: MEALPLAN_DAYS_DEFAULT,
            mealsPerDay: MEALPLAN_MEALS_PER_DAY,
            allergies: [],
            preferences: profileRef.current.cuisines.map((cuisine) => tCuisine(cuisine)),
          });
    setGenerating(false);
    if (result.ok) return 'ok';
    return result.status === 429 ? 'rate-limited' : 'failed';
  }, [tCuisine]);

  /** FR-401: 로그아웃 — 204 성공 (401 은 이미 만료된 세션이므로 성공 취급) + visited 마커 */
  const logout = useCallback(async () => {
    setLoggingOut(true);
    const result = await postLogout();
    setLoggingOut(false);
    const success = result.ok || result.status === 401;
    if (success) {
      window.localStorage.setItem(VISITED_MARKER_KEY, '1');
    }
    return success;
  }, []);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  return {
    status,
    user,
    members,
    budget,
    planId,
    connections,
    profile,
    saving,
    togglingStore,
    generating,
    loggingOut,
    saveHousehold,
    saveBudget,
    savePreference,
    toggleStore,
    regenerate,
    logout,
    reload,
  };
}
