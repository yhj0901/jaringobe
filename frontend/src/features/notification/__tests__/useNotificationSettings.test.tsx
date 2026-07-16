import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useNotificationSettings } from '@/features/notification/useNotificationSettings';
import {
  fetchNotificationSettings,
  putNotificationSettings,
} from '@/features/notification/api';
import type { NotificationSetting } from '@/features/notification/types';
import type { ApiResult } from '@/shared/api/client';

vi.mock('@/features/notification/api', () => ({
  fetchNotificationSettings: vi.fn(),
  putNotificationSettings: vi.fn(),
}));

const fetchMock = vi.mocked(fetchNotificationSettings);
const putMock = vi.mocked(putNotificationSettings);

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function err(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

const SETTINGS: NotificationSetting[] = [
  { type: 'meal_reminder_breakfast', enabled: true, localTime: '08:00', timezone: 'Asia/Seoul' },
  { type: 'meal_reminder_lunch', enabled: true, localTime: '12:00', timezone: 'Asia/Seoul' },
  { type: 'meal_reminder_dinner', enabled: true, localTime: '18:30', timezone: 'Asia/Seoul' },
  { type: 'mealplan_done', enabled: true, localTime: null, timezone: null },
  { type: 'weekly_nudge', enabled: false, localTime: null, timezone: null },
];

beforeEach(() => {
  vi.clearAllMocks();
});

async function renderReady() {
  fetchMock.mockResolvedValue(ok({ settings: SETTINGS }));
  const rendered = renderHook(() => useNotificationSettings());
  await waitFor(() => expect(rendered.result.current.status).toBe('ready'));
  return rendered;
}

describe('useNotificationSettings 조회 (api-spec 6-A-3)', () => {
  it('성공 → ready + settings', async () => {
    const { result } = await renderReady();
    expect(result.current.settings).toEqual(SETTINGS);
  });

  it('401 → unauthenticated / 5xx → error + reload 재시도', async () => {
    fetchMock.mockResolvedValueOnce(err(401, 'AUTH_REQUIRED'));
    const first = renderHook(() => useNotificationSettings());
    await waitFor(() => expect(first.result.current.status).toBe('unauthenticated'));

    fetchMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    const second = renderHook(() => useNotificationSettings());
    await waitFor(() => expect(second.result.current.status).toBe('error'));

    fetchMock.mockResolvedValueOnce(ok({ settings: SETTINGS }));
    act(() => second.result.current.reload());
    await waitFor(() => expect(second.result.current.status).toBe('ready'));
  });
});

describe('useNotificationSettings 행 단위 저장 — 낙관적 갱신·롤백 (ui-design 12장)', () => {
  it('성공: 낙관적 반영 후 서버 전체 settings 로 확정', async () => {
    const { result } = await renderReady();
    const serverSettings = SETTINGS.map((setting) =>
      setting.type === 'meal_reminder_dinner'
        ? { ...setting, localTime: '19:00' }
        : setting,
    );
    let resolvePut: (value: ApiResult<{ settings: NotificationSetting[] }>) => void = () => undefined;
    putMock.mockImplementation(
      () => new Promise((resolve) => (resolvePut = resolve)),
    );

    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.update('meal_reminder_dinner', { localTime: '19:00' });
    });

    // 낙관적 갱신 — 응답 전 즉시 반영 + 행 저장 중 표시
    await waitFor(() =>
      expect(
        result.current.settings.find((s) => s.type === 'meal_reminder_dinner')?.localTime,
      ).toBe('19:00'),
    );
    expect(result.current.savingTypes.has('meal_reminder_dinner')).toBe(true);

    await act(async () => {
      resolvePut(ok({ settings: serverSettings }));
      await pending;
    });
    expect(putMock).toHaveBeenCalledWith([{ type: 'meal_reminder_dinner', localTime: '19:00' }]);
    expect(result.current.settings).toEqual(serverSettings);
    expect(result.current.savingTypes.size).toBe(0);
    expect(result.current.updateError).toBe(false);
  });

  it('실패: 이전 값으로 롤백 + updateError → dismiss', async () => {
    const { result } = await renderReady();
    putMock.mockResolvedValue(err(500, 'UNKNOWN'));

    await act(() => result.current.update('mealplan_done', { enabled: false }));

    expect(result.current.settings.find((s) => s.type === 'mealplan_done')?.enabled).toBe(true);
    expect(result.current.updateError).toBe(true);
    expect(result.current.savingTypes.size).toBe(0);

    act(() => result.current.dismissError());
    expect(result.current.updateError).toBe(false);
  });

  it('같은 행 저장 중 재호출은 무시된다 (연타 방지)', async () => {
    const { result } = await renderReady();
    let resolvePut: (value: ApiResult<{ settings: NotificationSetting[] }>) => void = () => undefined;
    putMock.mockImplementation(() => new Promise((resolve) => (resolvePut = resolve)));

    let first: Promise<void> = Promise.resolve();
    act(() => {
      first = result.current.update('meal_reminder_lunch', { enabled: false });
    });
    await waitFor(() => expect(result.current.savingTypes.has('meal_reminder_lunch')).toBe(true));
    await act(() => result.current.update('meal_reminder_lunch', { enabled: true }));
    expect(putMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolvePut(ok({ settings: SETTINGS }));
      await first;
    });
    expect(result.current.savingTypes.size).toBe(0);
  });
});
