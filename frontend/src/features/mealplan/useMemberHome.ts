'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchMe } from '@/features/auth/useSession';
import {
  createOnboardingPlan,
  type CreateOnboardingPlanResult,
} from '@/features/budget/createOnboardingPlan';
import { createMealPlan, fetchLatestMealPlan, regenerateMealPlan } from '@/features/mealplan/api';
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
  generation: GenerationPhase;
  generationError: GenerationErrorKind | null;
  selectDate: (date: string) => void;
  createPlan: (input: PlanCreateInput) => Promise<void>;
  regeneratePlan: () => Promise<void>;
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
  const [selectedDate, setSelectedDate] = useState<string | undefined>(undefined);
  const [generation, setGeneration] = useState<GenerationPhase>('idle');
  const [generationError, setGenerationError] = useState<GenerationErrorKind | null>(null);

  const generationRef = useRef<GenerationPhase>('idle');
  const lastCreateInputRef = useRef<PlanCreateInput | null>(null);
  const lastActionRef = useRef<'create' | 'regenerate' | null>(null);
  const planRef = useRef<MealPlanResponse | null>(null);

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
    await loadLatest();
  }, [loadLatest]);

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
    generation,
    generationError,
    selectDate,
    createPlan,
    regeneratePlan,
    retryGenerate,
    dismissGenerationError,
    completeBudgetPlan,
    reload,
  };
}
