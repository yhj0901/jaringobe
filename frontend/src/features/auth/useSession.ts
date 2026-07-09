'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiFetch, type ApiResult } from '@/shared/api/client';
import type { UserMeResponse } from '@/shared/api/types';

/** GET /api/v1/users/me 래핑 (api-spec 1-5) — 로그인 직후 분기 판정용 단일 콜 */
export function fetchMe(): Promise<ApiResult<UserMeResponse>> {
  return apiFetch<UserMeResponse>('/api/v1/users/me');
}

export type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

interface SessionState {
  status: SessionStatus;
  user: UserMeResponse | null;
  refresh: () => Promise<void>;
}

/** 세션 훅 — 마운트 시 /users/me 1회 조회 (ui-design 2장 useSession) */
export function useSession(): SessionState {
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<UserMeResponse | null>(null);

  const refresh = useCallback(async () => {
    const result = await fetchMe();
    if (result.ok) {
      setUser(result.data);
      setStatus('authenticated');
    } else {
      setUser(null);
      setStatus(result.status === 401 ? 'unauthenticated' : 'error');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { status, user, refresh };
}
