import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useSession } from '@/features/auth/useSession';

function mockFetch(status: number, jsonBody: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(jsonBody),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useSession (api-spec 1-5)', () => {
  it('200 → authenticated + 유저 반환', async () => {
    mockFetch(200, { id: 'u1', nickname: '자린이', hasBudgetPlan: false });
    const { result } = renderHook(() => useSession());
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('authenticated'));
    expect(result.current.user?.id).toBe('u1');
  });

  it('401 → unauthenticated', async () => {
    mockFetch(401, { detail: { code: 'AUTH_REQUIRED', message: '' } });
    const { result } = renderHook(() => useSession());
    await waitFor(() => expect(result.current.status).toBe('unauthenticated'));
    expect(result.current.user).toBeNull();
  });

  it('5xx → error', async () => {
    mockFetch(500, {});
    const { result } = renderHook(() => useSession());
    await waitFor(() => expect(result.current.status).toBe('error'));
  });
});
