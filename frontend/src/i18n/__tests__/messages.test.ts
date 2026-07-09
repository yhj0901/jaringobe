import { describe, expect, it } from 'vitest';
import koMessages from '@messages/ko.json';
import enMessages from '@messages/en.json';

/** 중첩 객체를 dot-path 키 목록으로 평탄화 */
function flattenKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([key, value]) => {
    const path = prefix === '' ? key : `${prefix}.${key}`;
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      return flattenKeys(value as Record<string, unknown>, path);
    }
    return [path];
  });
}

describe('i18n 메시지 ko/en 동치성 (CLAUDE.md 동시 수정 규칙)', () => {
  it('ko.json 과 en.json 의 키 집합이 동일하다', () => {
    const koKeys = flattenKeys(koMessages).sort();
    const enKeys = flattenKeys(enMessages).sort();
    expect(koKeys).toEqual(enKeys);
  });

  it('빈 문자열 값이 없다 (빈 키 금지)', () => {
    const check = (obj: Record<string, unknown>, locale: string) => {
      for (const key of flattenKeys(obj)) {
        const value = key
          .split('.')
          .reduce<unknown>((acc, part) => (acc as Record<string, unknown>)[part], obj);
        expect(typeof value, `${locale}:${key}`).toBe('string');
        expect((value as string).length, `${locale}:${key}`).toBeGreaterThan(0);
      }
    };
    check(koMessages, 'ko');
    check(enMessages, 'en');
  });

  it('api-spec 의 에러 코드가 모두 auth.error 에 정의되어 있다', () => {
    const codes = [
      'AUTH_PROVIDER_DENIED',
      'AUTH_INVALID_STATE',
      'AUTH_PROVIDER_ERROR',
      'AUTH_REQUIRED',
      'AUTH_TOKEN_REVOKED',
      'FORBIDDEN_ORIGIN',
      'VALIDATION_ERROR',
      'RATE_LIMITED',
      'BUDGET_PLAN_EXISTS',
      'PROVIDER_NOT_SUPPORTED',
    ];
    for (const messages of [koMessages, enMessages]) {
      const errorKeys = Object.keys(messages.auth.error);
      for (const code of codes) {
        expect(errorKeys).toContain(code);
      }
    }
    expect(koMessages.auth.notice.AUTH_EMAIL_CONFLICT_NOTICE).toBeDefined();
    expect(enMessages.auth.notice.AUTH_EMAIL_CONFLICT_NOTICE).toBeDefined();
  });
});
