import { describe, expect, it } from 'vitest';
import {
  isValidBudgetAmount,
  isValidHouseholdSize,
} from '@/features/guest/budgetDraftValidation';

describe('isValidHouseholdSize (FR-104)', () => {
  it('1~10 정수만 허용한다', () => {
    expect(isValidHouseholdSize(1)).toBe(true);
    expect(isValidHouseholdSize(10)).toBe(true);
    expect(isValidHouseholdSize(0)).toBe(false);
    expect(isValidHouseholdSize(11)).toBe(false);
    expect(isValidHouseholdSize(2.5)).toBe(false);
    expect(isValidHouseholdSize(-1)).toBe(false);
  });
});

describe('isValidBudgetAmount (CWE-20, api-spec 범위와 동일)', () => {
  it('KRW 는 5만~500만 범위만 허용한다', () => {
    expect(isValidBudgetAmount('50000', 'KRW')).toBe(true);
    expect(isValidBudgetAmount('5000000', 'KRW')).toBe(true);
    expect(isValidBudgetAmount('49999', 'KRW')).toBe(false);
    expect(isValidBudgetAmount('5000001', 'KRW')).toBe(false);
  });

  it('USD 는 50~5000 범위만 허용한다', () => {
    expect(isValidBudgetAmount('50', 'USD')).toBe(true);
    expect(isValidBudgetAmount('5000', 'USD')).toBe(true);
    expect(isValidBudgetAmount('49', 'USD')).toBe(false);
    expect(isValidBudgetAmount('5001', 'USD')).toBe(false);
  });

  it('정수 형식이 아닌 입력을 거부한다', () => {
    expect(isValidBudgetAmount('', 'KRW')).toBe(false);
    expect(isValidBudgetAmount('abc', 'KRW')).toBe(false);
    expect(isValidBudgetAmount('-100000', 'KRW')).toBe(false);
    expect(isValidBudgetAmount('100000.5', 'KRW')).toBe(false);
    expect(isValidBudgetAmount('1e6', 'KRW')).toBe(false);
    expect(isValidBudgetAmount('100 000', 'KRW')).toBe(false);
  });
});
