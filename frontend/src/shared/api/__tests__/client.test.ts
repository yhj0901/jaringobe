import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, errorCodeToI18nKey, NETWORK_ERROR_CODE } from '@/shared/api/client';

function mockFetchOnce(response: Partial<Response> & { jsonBody?: unknown }) {
  const { jsonBody, ...rest } = response;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: rest.ok ?? true,
      status: rest.status ?? 200,
      json: () =>
        jsonBody === undefined ? Promise.reject(new Error('no body')) : Promise.resolve(jsonBody),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('errorCodeToI18nKey', () => {
  it('알려진 코드는 auth.error.{code} 로 매핑한다', () => {
    expect(errorCodeToI18nKey('AUTH_INVALID_STATE')).toBe('auth.error.AUTH_INVALID_STATE');
    expect(errorCodeToI18nKey('BUDGET_PLAN_EXISTS')).toBe('auth.error.BUDGET_PLAN_EXISTS');
  });

  it('미정의 코드/undefined 는 common.error.fallback 으로 매핑한다', () => {
    expect(errorCodeToI18nKey('SOMETHING_NEW')).toBe('common.error.fallback');
    expect(errorCodeToI18nKey(undefined)).toBe('common.error.fallback');
  });
});

describe('apiFetch', () => {
  it('200 응답의 JSON 을 반환한다', async () => {
    mockFetchOnce({ ok: true, status: 200, jsonBody: { id: 'u1' } });
    const result = await apiFetch<{ id: string }>('/api/v1/users/me');
    expect(result).toEqual({ ok: true, status: 200, data: { id: 'u1' } });
  });

  it('204 응답은 본문 없이 성공 처리한다', async () => {
    mockFetchOnce({ ok: true, status: 204 });
    const result = await apiFetch<undefined>('/api/v1/auth/logout', { method: 'POST' });
    expect(result.ok).toBe(true);
    expect(result.status).toBe(204);
  });

  it('에러 응답의 detail.code 를 i18n 키로 매핑한다', async () => {
    mockFetchOnce({
      ok: false,
      status: 401,
      jsonBody: { detail: { code: 'AUTH_REQUIRED', message: 'auth required' } },
    });
    const result = await apiFetch('/api/v1/users/me');
    expect(result).toEqual({
      ok: false,
      status: 401,
      code: 'AUTH_REQUIRED',
      i18nKey: 'auth.error.AUTH_REQUIRED',
    });
  });

  it('detail 구조가 아니면 fallback 키를 사용한다', async () => {
    mockFetchOnce({ ok: false, status: 500, jsonBody: { message: 'oops' } });
    const result = await apiFetch('/api/v1/users/me');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.code).toBe('UNKNOWN');
      expect(result.i18nKey).toBe('common.error.fallback');
    }
  });

  it('JSON 파싱 실패 시에도 fallback 처리한다', async () => {
    mockFetchOnce({ ok: false, status: 502 });
    const result = await apiFetch('/api/v1/users/me');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.i18nKey).toBe('common.error.fallback');
    }
  });

  it('네트워크 오류 시 NETWORK_ERROR 코드를 반환한다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')));
    const result = await apiFetch('/api/v1/users/me');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(0);
      expect(result.code).toBe(NETWORK_ERROR_CODE);
      expect(result.i18nKey).toBe('common.error.fallback');
    }
  });

  it('Content-Type JSON 과 same-origin 자격증명을 기본 적용한다', async () => {
    mockFetchOnce({ ok: true, status: 200, jsonBody: {} });
    await apiFetch('/api/v1/users/me');
    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/users/me',
      expect.objectContaining({
        credentials: 'same-origin',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
  });
});
