'use client';

import { useCallback, useEffect, useState } from 'react';
import { fetchCycle, postCycleSkip, putCycleSettings } from '@/features/cycle/api';
import type { CycleSettingsUpdate, CycleState } from '@/features/cycle/types';

export type CycleLoadStatus = 'loading' | 'ready' | 'unauthenticated' | 'error';

export interface CycleHookState {
  status: CycleLoadStatus;
  cycle: CycleState | null;
  saving: boolean;
  errorCode: string | null;
  reload: () => void;
  updateSettings: (body: CycleSettingsUpdate) => Promise<boolean>;
  skip: () => Promise<boolean>;
}

/** cycle 세 엔드포인트가 같은 CycleState를 반환하므로 한 훅에서 서버 상태를 갱신한다. */
export function useCycle(): CycleHookState {
  const [status, setStatus] = useState<CycleLoadStatus>('loading');
  const [cycle, setCycle] = useState<CycleState | null>(null);
  const [saving, setSaving] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    setErrorCode(null);
    const result = await fetchCycle();
    if (result.ok) {
      setCycle(result.data);
      setStatus('ready');
      return;
    }
    setCycle(null);
    setErrorCode(result.code);
    setStatus(result.status === 401 ? 'unauthenticated' : 'error');
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateSettings = useCallback(async (body: CycleSettingsUpdate) => {
    setSaving(true);
    setErrorCode(null);
    const result = await putCycleSettings(body);
    setSaving(false);
    if (!result.ok) {
      setErrorCode(result.code);
      return false;
    }
    setCycle(result.data);
    setStatus('ready');
    return true;
  }, []);

  const skip = useCallback(async () => {
    setSaving(true);
    setErrorCode(null);
    const result = await postCycleSkip();
    setSaving(false);
    if (!result.ok) {
      setErrorCode(result.code);
      return false;
    }
    setCycle(result.data);
    setStatus('ready');
    return true;
  }, []);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  return { status, cycle, saving, errorCode, reload, updateSettings, skip };
}
