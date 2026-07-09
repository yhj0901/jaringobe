import {
  BUDGET_RANGE,
  HOUSEHOLD_MAX,
  HOUSEHOLD_MIN,
} from '@/shared/config/constants';
import type { Money } from '@/shared/api/types';

/**
 * 예산안 작성 클라이언트 검증 (FR-104, CWE-20)
 * 서버(api-spec 2-1) 검증 범위와 동일 — 정수 연산만 사용 (float 금지).
 */

export function isValidHouseholdSize(size: number): boolean {
  return Number.isInteger(size) && size >= HOUSEHOLD_MIN && size <= HOUSEHOLD_MAX;
}

/** 금액 문자열이 정수 형식 + 통화별 허용 범위인지 검증 */
export function isValidBudgetAmount(amount: string, currency: Money['currency']): boolean {
  if (!/^\d+$/.test(amount)) return false;
  const value = Number.parseInt(amount, 10);
  if (!Number.isSafeInteger(value)) return false;
  const range = BUDGET_RANGE[currency];
  return value >= range.min && value <= range.max;
}
