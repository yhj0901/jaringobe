'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchNotificationSettings,
  putNotificationSettings,
} from '@/features/notification/api';
import type {
  NotificationSetting,
  NotificationType,
} from '@/features/notification/types';

/**
 * 알림 설정 데이터 어댑터 (ui-design 12장, FR-007)
 * 행 단위 변경 즉시 PUT — 낙관적 갱신·실패 롤백 (완료 버튼 없음).
 */

export type NotificationSettingsStatus = 'loading' | 'unauthenticated' | 'error' | 'ready';

/** 행 단위 변경 패치 — enabled 토글 또는 리마인더 시각 */
export interface SettingPatch {
  enabled?: boolean;
  localTime?: string;
}

export interface NotificationSettingsState {
  status: NotificationSettingsStatus;
  settings: NotificationSetting[];
  /** 저장 진행 중인 type 집합 — 행 연타 방지 */
  savingTypes: ReadonlySet<NotificationType>;
  /** 직전 저장 실패 여부 — 배너 표시 후 dismiss */
  updateError: boolean;
  update: (type: NotificationType, patch: SettingPatch) => Promise<void>;
  dismissError: () => void;
  reload: () => void;
}

export function useNotificationSettings(): NotificationSettingsState {
  const [status, setStatus] = useState<NotificationSettingsStatus>('loading');
  const [settings, setSettings] = useState<NotificationSetting[]>([]);
  const [savingTypes, setSavingTypes] = useState<ReadonlySet<NotificationType>>(new Set());
  const [updateError, setUpdateError] = useState(false);

  const settingsRef = useRef<NotificationSetting[]>([]);
  const savingRef = useRef<Set<NotificationType>>(new Set());

  const applySettings = useCallback((next: NotificationSetting[]) => {
    settingsRef.current = next;
    setSettings(next);
  }, []);

  const syncSaving = useCallback((next: Set<NotificationType>) => {
    savingRef.current = next;
    setSavingTypes(new Set(next));
  }, []);

  const load = useCallback(async () => {
    setStatus('loading');
    const result = await fetchNotificationSettings();
    if (result.ok) {
      applySettings(result.data.settings);
      setStatus('ready');
      return;
    }
    setStatus(result.status === 401 ? 'unauthenticated' : 'error');
  }, [applySettings]);

  useEffect(() => {
    void load();
  }, [load]);

  /** 행 단위 즉시 저장 — 낙관적 갱신 후 실패 시 이전 값으로 롤백 (ui-design 12장) */
  const update = useCallback(
    async (type: NotificationType, patch: SettingPatch) => {
      if (savingRef.current.has(type)) return; // 행 연타 방지

      const previous = settingsRef.current;
      const optimistic = previous.map((setting) =>
        setting.type === type ? { ...setting, ...patch } : setting,
      );
      applySettings(optimistic);
      setUpdateError(false);

      const addSaving = new Set(savingRef.current);
      addSaving.add(type);
      syncSaving(addSaving);

      const result = await putNotificationSettings([{ type, ...patch }]);
      if (result.ok) {
        // 서버 진실(전체 settings 재반환)로 확정 (api-spec 6-A-4)
        applySettings(result.data.settings);
      } else {
        applySettings(previous); // 실패 → 롤백
        setUpdateError(true);
      }

      const clearSaving = new Set(savingRef.current);
      clearSaving.delete(type);
      syncSaving(clearSaving);
    },
    [applySettings, syncSaving],
  );

  const dismissError = useCallback(() => setUpdateError(false), []);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  return { status, settings, savingTypes, updateError, update, dismissError, reload };
}
