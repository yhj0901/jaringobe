import { PLAN_ITEMS_MAX_COUNT, PLAN_ITEM_MAX_LENGTH } from '@/features/mealplan/constants';

/**
 * 생성 시트 알레르기/선호 칩 입력 클라이언트 검증 (FR-203, api-spec 3-2 서버 검증과 동일)
 * — 항목당 30자, 목록당 최대 10개, 중복 금지. 빈 입력은 조용히 무시(에러 미표시).
 */

export type ChipValidationError = 'empty' | 'too-long' | 'too-many' | 'duplicate';

export type ChipValidationResult =
  | { ok: true; value: string }
  | { ok: false; error: ChipValidationError };

export function validateChipItem(
  raw: string,
  existing: readonly string[],
): ChipValidationResult {
  const value = raw.trim();
  if (value === '') return { ok: false, error: 'empty' };
  if (value.length > PLAN_ITEM_MAX_LENGTH) return { ok: false, error: 'too-long' };
  if (existing.length >= PLAN_ITEMS_MAX_COUNT) return { ok: false, error: 'too-many' };
  if (existing.includes(value)) return { ok: false, error: 'duplicate' };
  return { ok: true, value };
}
