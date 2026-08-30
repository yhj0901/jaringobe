import type { Money } from '@/shared/api/types';
import type { OrderBlockedReason } from '@/features/order/types';

export type CycleFrequency = 'weekly' | 'biweekly';

export type CycleStage =
  | 'idle'
  | 'generating'
  | 'generated'
  | 'generate_failed'
  | 'drafted'
  | 'awaiting_user'
  | 'confirmed'
  | 'delivered'
  | 'nothing_to_order'
  | 'skipped_user'
  | 'skipped_dormant'
  | 'deferred_quota'
  | 'paused';

export interface CycleMealPlanSummary {
  id: string;
  status: string;
}

export interface CycleDraftOrderSummary {
  id: string;
  status: 'draft' | 'awaiting_user';
  estimatedTotal: Money;
  autoConfirmAt: string | null;
  blockedReason: OrderBlockedReason | null;
  deliveryEta: string | null;
}

/** GET/PUT/POST cycle 엔드포인트 공통 응답 (api-spec 9장 v1.8). */
export interface CycleState {
  enabled: boolean;
  frequency: CycleFrequency;
  anchorWeekday: number;
  timezone: string;
  autoConfirm: boolean;
  cycleStart: string;
  cycleDays: number;
  stage: CycleStage;
  nextRunAt: string | null;
  skippedCycleStart: string | null;
  weeklyLimit: Money | null;
  mealPlan: CycleMealPlanSummary | null;
  draftOrder: CycleDraftOrderSummary | null;
  simulation: boolean;
}

export interface CycleSettingsUpdate {
  enabled?: boolean;
  frequency?: CycleFrequency;
  anchorWeekday?: number;
  timezone?: string;
  autoConfirm?: boolean;
}
