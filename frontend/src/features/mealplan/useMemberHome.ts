'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchMe } from '@/features/auth/useSession';
import {
  createOnboardingPlan,
  type CreateOnboardingPlanResult,
} from '@/features/budget/createOnboardingPlan';
import {
  createMealPlan,
  fetchLatestMealPlan,
  regenerateMealPlan,
  setMealCompletion,
} from '@/features/mealplan/api';
import { fetchHousehold } from '@/features/household/api';
import {
  MEALPLAN_MEALS_PER_DAY,
  MEALPLAN_NOT_FOUND_CODE,
} from '@/features/mealplan/constants';
import { defaultSelectedDate, mapPlanToViewModel } from '@/features/mealplan/mapPlanToViewModel';
import type { MealPlanResponse } from '@/features/mealplan/types';
import type { HomeViewModel } from '@/features/home/types';
import type { GuestPlan } from '@/features/guest/store';
import type { Money } from '@/shared/api/types';
import type { ApiResult } from '@/shared/api/client';

/**
 * 회원 홈 데이터 어댑터 (ui-design 7장, FR-201)
 * GET /users/me → hasBudgetPlan 분기 → GET /mealplans/latest 분기 → HomeViewModel.
 */

export type MemberHomeStatus =
  | 'loading' // 초기 me/latest 조회 중 — 스켈레톤
  | 'guest' // 401 (쿠키 만료 등) — 게스트 홈 폴백
  | 'budget-required' // hasBudgetPlan=false — BudgetPlanGate (FR-207)
  | 'empty' // 식단 없음 (404 MEALPLAN_NOT_FOUND) — EmptyPlanHero (FR-202)
  | 'ready' // 최신 식단 표시 (FR-205)
  | 'error'; // 조회 실패

export type GenerationPhase = 'idle' | 'creating' | 'regenerating';
export type GenerationErrorKind = 'rate-limited' | 'failed';

/** 생성 시트 제출 입력 — mealsPerDay 는 3끼 고정이라 훅이 채운다 (FR-203) */
export interface PlanCreateInput {
  days: number;
  allergies: string[];
  preferences: string[];
}

export interface MemberHomeState {
  status: MemberHomeStatus;
  /** users/me.onboardingCompleted — 진입 배너 분기 (FR-316, ui-design 8장). 조회 전 null */
  onboardingCompleted: boolean | null;
  plan: MealPlanResponse | null;
  /** 표시용 ViewModel — status='ready' 일 때만 존재 */
  viewModel: HomeViewModel | null;
  /** 온보딩 예산안 작성 직후 확정된 예산 — 빈 상태 히어로 금액 (FR-202) */
  budget: Money | null;
  /** 가구 인원 — 레시피 시트 "N인분" (FR-504). 조회 전/실패 시 null */
  householdSize: number | null;
  generation: GenerationPhase;
  generationError: GenerationErrorKind | null;
  /** 완료 토글 진행 중인 끼니 id 집합 — 연타 방지 (FR-503) */
  pendingMealIds: ReadonlySet<string>;
  selectDate: (date: string) => void;
  createPlan: (input: PlanCreateInput) => Promise<void>;
  regeneratePlan: () => Promise<void>;
  /** 끼니 완료 설정/해제 — 낙관적 갱신 + 실패 롤백 (FR-501/503) */
  toggleMealCompletion: (mealId: string) => Promise<void>;
  /** 실패 배너의 재시도 — 마지막 생성/재생성 요청을 그대로 재실행 (FR-204) */
  retryGenerate: () => Promise<void>;
  dismissGenerationError: () => void;
  completeBudgetPlan: (plan: GuestPlan) => Promise<CreateOnboardingPlanResult['kind']>;
  reload: () => void;
}

export function useMemberHome(): MemberHomeState {
  const [status, setStatus] = useState<MemberHomeStatus>('loading');
  const [onboardingCompleted, setOnboardingCompleted] = useState<boolean | null>(null);
  const [plan, setPlan] = useState<MealPlanResponse | null>(null);
  const [budget, setBudget] = useState<Money | null>(null);
  const [householdSize, setHouseholdSize] = useState<number | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | undefined>(undefined);
  const [generation, setGeneration] = useState<GenerationPhase>('idle');
  const [generationError, setGenerationError] = useState<GenerationErrorKind | null>(null);
  const [pendingMealIds, setPendingMealIds] = useState<ReadonlySet<string>>(new Set());

  const generationRef = useRef<GenerationPhase>('idle');
  const lastCreateInputRef = useRef<PlanCreateInput | null>(null);
  const lastActionRef = useRef<'create' | 'regenerate' | null>(null);
  const planRef = useRef<MealPlanResponse | null>(null);
  const pendingRef = useRef<Set<string>>(new Set());

  const applyPlan = useCallback((next: MealPlanResponse) => {
    planRef.current = next;
    setPlan(next);
    setSelectedDate(defaultSelectedDate(next));
    setStatus('ready');
  }, []);

  const loadLatest = useCallback(async () => {
    const result = await fetchLatestMealPlan();
    if (result.ok) {
      applyPlan(result.data);
      return;
    }
    if (result.status === 404 && result.code === MEALPLAN_NOT_FOUND_CODE) {
      setStatus('empty');
      return;
    }
    setStatus('error');
  }, [applyPlan]);

  /** 가구 인원 조회 — 레시피 "N인분" 표시용. 실패(404 등)해도 홈 흐름은 계속 (기본값 폴백) */
  const loadHousehold = useCallback(async () => {
    const result = await fetchHousehold();
    setHouseholdSize(result.ok ? result.data.size : null);
  }, []);

  const load = useCallback(async () => {
    setStatus('loading');
    const me = await fetchMe();
    if (!me.ok) {
      setStatus(me.status === 401 ? 'guest' : 'error');
      return;
    }
    setOnboardingCompleted(me.data.onboardingCompleted);
    if (!me.data.hasBudgetPlan) {
      setStatus('budget-required');
      return;
    }
    void loadHousehold();
    await loadLatest();
  }, [loadLatest, loadHousehold]);

  useEffect(() => {
    void load();
  }, [load]);

  /** 생성/재생성 공통 실행 — 진행 중이면 무시(연타 방지), 429 → 대기 안내 (FR-204) */
  const runGeneration = useCallback(
    async (phase: Exclude<GenerationPhase, 'idle'>, exec: () => Promise<ApiResult<MealPlanResponse>>) => {
      if (generationRef.current !== 'idle') return;
      generationRef.current = phase;
      setGeneration(phase);
      setGenerationError(null);
      const result = await exec();
      if (result.ok) {
        applyPlan(result.data);
      } else {
        setGenerationError(result.status === 429 ? 'rate-limited' : 'failed');
      }
      generationRef.current = 'idle';
      setGeneration('idle');
    },
    [applyPlan],
  );

  const createPlan = useCallback(
    async (input: PlanCreateInput) => {
      lastActionRef.current = 'create';
      lastCreateInputRef.current = input;
      await runGeneration('creating', () =>
        createMealPlan({
          days: input.days,
          mealsPerDay: MEALPLAN_MEALS_PER_DAY,
          allergies: input.allergies,
          preferences: input.preferences,
        }),
      );
    },
    [runGeneration],
  );

  const regeneratePlan = useCallback(async () => {
    const current = planRef.current;
    if (current === null) return;
    lastActionRef.current = 'regenerate';
    await runGeneration('regenerating', () => regenerateMealPlan(current.id));
  }, [runGeneration]);

  const retryGenerate = useCallback(async () => {
    if (lastActionRef.current === 'create' && lastCreateInputRef.current !== null) {
      await createPlan(lastCreateInputRef.current);
      return;
    }
    if (lastActionRef.current === 'regenerate') {
      await regeneratePlan();
    }
  }, [createPlan, regeneratePlan]);

  const dismissGenerationError = useCallback(() => setGenerationError(null), []);

  /** pendingRef 와 렌더용 state 동기화 */
  const syncPending = useCallback((next: Set<string>) => {
    pendingRef.current = next;
    setPendingMealIds(new Set(next));
  }, []);

  const toggleMealCompletion = useCallback(
    async (mealId: string) => {
      const current = planRef.current;
      if (current === null) return;
      if (pendingRef.current.has(mealId)) return; // 연타 방지 (FR-503)
      const target = current.meals.find((meal) => meal.id === mealId);
      if (target === undefined) return;

      const previousCompletedAt = target.completedAt ?? null;
      const nextCompleted = previousCompletedAt === null;
      const optimisticAt = nextCompleted ? new Date().toISOString() : null;

      // 낙관적 갱신 — selectedDate 는 유지 (applyPlan 미사용)
      const optimisticPlan: MealPlanResponse = {
        ...current,
        meals: current.meals.map((meal) =>
          meal.id === mealId ? { ...meal, completedAt: optimisticAt } : meal,
        ),
      };
      planRef.current = optimisticPlan;
      setPlan(optimisticPlan);

      const addPending = new Set(pendingRef.current);
      addPending.add(mealId);
      syncPending(addPending);

      const result = await setMealCompletion(current.id, mealId, nextCompleted);

      const base = planRef.current ?? optimisticPlan;
      if (result.ok) {
        // 서버 진실(MealOut)로 해당 끼니 병합
        const server = result.data;
        const merged: MealPlanResponse = {
          ...base,
          meals: base.meals.map((meal) => (meal.id === mealId ? { ...meal, ...server } : meal)),
        };
        planRef.current = merged;
        setPlan(merged);
      } else {
        // 실패 → 이전 완료 상태로 롤백
        const rolledBack: MealPlanResponse = {
          ...base,
          meals: base.meals.map((meal) =>
            meal.id === mealId ? { ...meal, completedAt: previousCompletedAt } : meal,
          ),
        };
        planRef.current = rolledBack;
        setPlan(rolledBack);
      }

      const clearPending = new Set(pendingRef.current);
      clearPending.delete(mealId);
      syncPending(clearPending);
    },
    [syncPending],
  );

  const completeBudgetPlan = useCallback(
    async (guestPlan: GuestPlan) => {
      const result = await createOnboardingPlan(guestPlan);
      if (result.kind === 'created') {
        setBudget(result.plan.budget);
        setStatus('empty');
      } else if (result.kind === 'already-exists') {
        // 경합으로 이미 예산안 보유 — 최신 식단 재조회 (api-spec 2-1)
        setStatus('loading');
        await loadLatest();
      }
      return result.kind;
    },
    [loadLatest],
  );

  const selectDate = useCallback((date: string) => setSelectedDate(date), []);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  const viewModel = useMemo(() => {
    if (status !== 'ready' || plan === null) return null;
    return mapPlanToViewModel(plan, { selectedDate });
  }, [status, plan, selectedDate]);

  return {
    status,
    onboardingCompleted,
    plan,
    viewModel,
    budget,
    householdSize,
    generation,
    generationError,
    pendingMealIds,
    selectDate,
    createPlan,
    regeneratePlan,
    toggleMealCompletion,
    retryGenerate,
    dismissGenerationError,
    completeBudgetPlan,
    reload,
  };
}
