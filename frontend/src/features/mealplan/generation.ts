import { fetchLatestMealPlan, fetchMealPlan } from '@/features/mealplan/api';
import {
  MEALPLAN_GENERATING_CODE,
  MEALPLAN_POLL_BACKOFF_AFTER,
  MEALPLAN_POLL_BACKOFF_MS,
  MEALPLAN_POLL_INTERVAL_MS,
  MEALPLAN_POLL_MAX_MS,
} from '@/features/mealplan/constants';
import type {
  MealPlanAcceptedResponse,
  MealPlanResponse,
  MealPlanStatus,
} from '@/features/mealplan/types';
import type { ApiResult } from '@/shared/api/client';

/**
 * 생성 비동기 폴링 공통 로직 (ui-design 12장, api-spec 3-2/3-3 v1.5)
 * POST 202 → GET /mealplans/{id} 3초 폴링(백오프 5초, 최대 3분).
 * 409 MEALPLAN_GENERATING 은 진행 중 플랜 폴링에 합류. 푸시는 보조 채널 — 화면 폴링이 기본.
 */

/** 표시 가능한 완료 상태 (ready/over_budget) */
export function isDisplayableStatus(status: MealPlanStatus): boolean {
  return status === 'ready' || status === 'over_budget';
}

export type GenerationOutcome =
  | { kind: 'completed'; plan: MealPlanResponse } // ready | over_budget
  | { kind: 'failed' } // status=failed 또는 폴링 지속 불가/시작 실패
  | { kind: 'timeout' } // 3분 초과 — "완료되면 알려드릴게요" 안내 (생성은 서버에서 계속)
  | { kind: 'rate-limited' }; // 429

export interface PollOptions {
  intervalMs?: number;
  backoffMs?: number;
  backoffAfter?: number;
  maxDurationMs?: number;
  /** 테스트 주입용 대기 함수 */
  sleep?: (ms: number) => Promise<void>;
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

/**
 * GET /mealplans/{id} 폴링 — 첫 조회는 즉시, 이후 3초 간격(10회 이후 5초 백오프).
 * 일시 오류(네트워크/5xx)는 계속, 401/403/404 는 지속 불가로 failed 처리.
 */
export async function pollMealPlan(
  planId: string,
  options: PollOptions = {},
): Promise<GenerationOutcome> {
  const intervalMs = options.intervalMs ?? MEALPLAN_POLL_INTERVAL_MS;
  const backoffMs = options.backoffMs ?? MEALPLAN_POLL_BACKOFF_MS;
  const backoffAfter = options.backoffAfter ?? MEALPLAN_POLL_BACKOFF_AFTER;
  const maxDurationMs = options.maxDurationMs ?? MEALPLAN_POLL_MAX_MS;
  const sleep = options.sleep ?? defaultSleep;

  let elapsedMs = 0;
  let attempt = 0;

  for (;;) {
    const result = await fetchMealPlan(planId);
    if (result.ok) {
      if (isDisplayableStatus(result.data.status)) {
        return { kind: 'completed', plan: result.data };
      }
      if (result.data.status === 'failed') {
        return { kind: 'failed' };
      }
      // processing → 계속 폴링
    } else if (result.status === 401 || result.status === 403 || result.status === 404) {
      return { kind: 'failed' }; // 폴링 지속 불가 (세션 만료/권한/소실)
    }

    attempt += 1;
    const delayMs = attempt > backoffAfter ? backoffMs : intervalMs;
    if (elapsedMs + delayMs > maxDurationMs) {
      return { kind: 'timeout' };
    }
    elapsedMs += delayMs;
    await sleep(delayMs);
  }
}

type GenerationStart =
  | { kind: 'started'; planId: string }
  | { kind: 'completed'; plan: MealPlanResponse } // 409 합류 시점에 이미 완료된 플랜 (BUG-007)
  | { kind: 'rate-limited' }
  | { kind: 'failed' };

/**
 * 생성/재생성 시작 — 202 면 해당 id, 409 MEALPLAN_GENERATING 이면 진행 중 최신 플랜에 합류.
 * 합류 시점에 최신 플랜이 이미 완료(ready/over_budget)면 completed 로 처리한다 (BUG-007 — 성공을 실패로 표시 금지).
 */
export async function startGeneration(
  begin: () => Promise<ApiResult<MealPlanAcceptedResponse>>,
): Promise<GenerationStart> {
  const result = await begin();
  if (result.ok) return { kind: 'started', planId: result.data.id };
  if (result.status === 429) return { kind: 'rate-limited' };
  if (result.status === 409 && result.code === MEALPLAN_GENERATING_CODE) {
    // 진행 중 플랜 폴링 합류 (ui-design 12장)
    const latest = await fetchLatestMealPlan();
    if (latest.ok) {
      if (latest.data.status === 'processing') {
        return { kind: 'started', planId: latest.data.id };
      }
      if (isDisplayableStatus(latest.data.status)) {
        return { kind: 'completed', plan: latest.data };
      }
      // failed 등 그 외 상태는 기존대로 failed
    }
  }
  return { kind: 'failed' };
}

/** 시작(202/409 합류) + 폴링을 한 흐름으로 — 웹/앱 공통 (온보딩 8장 포함 동일 전환) */
export async function runGenerationFlow(
  begin: () => Promise<ApiResult<MealPlanAcceptedResponse>>,
  options?: PollOptions,
): Promise<GenerationOutcome> {
  const start = await startGeneration(begin);
  if (start.kind === 'completed') return start; // 이미 완료된 플랜 — 폴링 불필요 (BUG-007)
  if (start.kind !== 'started') {
    return start.kind === 'rate-limited' ? { kind: 'rate-limited' } : { kind: 'failed' };
  }
  return pollMealPlan(start.planId, options);
}
