import { describe, expect, it } from 'vitest';
import { validateChipItem } from '@/features/mealplan/planCreateValidation';
import {
  PLAN_ITEMS_MAX_COUNT,
  PLAN_ITEM_MAX_LENGTH,
} from '@/features/mealplan/constants';

describe('validateChipItem (FR-203, api-spec 3-2 검증과 동일)', () => {
  it('정상 입력은 trim 된 값을 돌려준다', () => {
    expect(validateChipItem('  땅콩  ', [])).toEqual({ ok: true, value: '땅콩' });
  });

  it('빈 입력/공백만 → empty', () => {
    expect(validateChipItem('', [])).toEqual({ ok: false, error: 'empty' });
    expect(validateChipItem('   ', [])).toEqual({ ok: false, error: 'empty' });
  });

  it('30자 초과 → too-long (경계: 30자는 허용)', () => {
    const exact = 'a'.repeat(PLAN_ITEM_MAX_LENGTH);
    expect(validateChipItem(exact, [])).toEqual({ ok: true, value: exact });
    expect(validateChipItem(`${exact}b`, [])).toEqual({ ok: false, error: 'too-long' });
  });

  it('기존 10개 → too-many', () => {
    const existing = Array.from({ length: PLAN_ITEMS_MAX_COUNT }, (_, i) => `item-${i}`);
    expect(validateChipItem('새 항목', existing)).toEqual({ ok: false, error: 'too-many' });
    expect(validateChipItem('새 항목', existing.slice(0, 9))).toEqual({
      ok: true,
      value: '새 항목',
    });
  });

  it('중복 항목 → duplicate', () => {
    expect(validateChipItem('땅콩', ['땅콩'])).toEqual({ ok: false, error: 'duplicate' });
  });
});
