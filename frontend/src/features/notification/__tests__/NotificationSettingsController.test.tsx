import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { NotificationSettingsController } from '@/features/notification/NotificationSettingsController';
import { useNotificationSettings, type NotificationSettingsState } from '@/features/notification/useNotificationSettings';
import { useBridgeStore } from '@/shared/bridge/store';
import { renderWithIntl } from '@/test/renderWithIntl';
import { stubAppEnvironment, type AppEnvStub } from '@/test/appEnv';
import type { NotificationSetting } from '@/features/notification/types';

const routerMock = { push: vi.fn(), replace: vi.fn() };

vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/settings/notifications',
  };
});
vi.mock('@/features/notification/useNotificationSettings', () => ({
  useNotificationSettings: vi.fn(),
}));

const stateMock = vi.mocked(useNotificationSettings);

const SETTINGS: NotificationSetting[] = [
  { type: 'meal_reminder_breakfast', enabled: true, localTime: '08:00', timezone: 'Asia/Seoul' },
  { type: 'meal_reminder_lunch', enabled: false, localTime: '12:00', timezone: 'Asia/Seoul' },
  { type: 'meal_reminder_dinner', enabled: true, localTime: null, timezone: 'Asia/Seoul' },
  { type: 'mealplan_done', enabled: true, localTime: null, timezone: null },
  { type: 'weekly_nudge', enabled: false, localTime: null, timezone: null },
];

function baseState(overrides: Partial<NotificationSettingsState> = {}): NotificationSettingsState {
  return {
    status: 'ready',
    settings: SETTINGS,
    savingTypes: new Set(),
    updateError: false,
    update: vi.fn().mockResolvedValue(undefined),
    dismissError: vi.fn(),
    reload: vi.fn(),
    ...overrides,
  };
}

let app: AppEnvStub | null = null;

beforeEach(() => {
  vi.clearAllMocks();
  useBridgeStore.getState().reset();
  stateMock.mockReturnValue(baseState());
});

afterEach(() => {
  app?.restore();
  app = null;
});

describe('NotificationSettingsController 상태 분기', () => {
  it('loading → aria-busy 스켈레톤', () => {
    stateMock.mockReturnValue(baseState({ status: 'loading', settings: [] }));
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('unauthenticated → /login?next=/settings/notifications 리다이렉트', async () => {
    stateMock.mockReturnValue(baseState({ status: 'unauthenticated', settings: [] }));
    renderWithIntl(<NotificationSettingsController />);
    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith('/login?next=/settings/notifications'),
    );
  });

  it('error → 안내 + 다시 불러오기', () => {
    const state = baseState({ status: 'error', settings: [] });
    stateMock.mockReturnValue(state);
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.getByRole('alert')).toHaveTextContent('알림 설정을 불러오지 못했어요');
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(state.reload).toHaveBeenCalledTimes(1);
  });
});

describe('NotificationSettingsController — 토글·시각 저장 (FR-007, ui-design 12장)', () => {
  it('식단 완성 토글 + 리마인더 3행(아침/점심/저녁)을 렌더한다 — weekly_nudge 미노출', () => {
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.getByRole('switch', { name: '식단 완성 알림' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('switch', { name: '아침 리마인더 알림' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('switch', { name: '점심 리마인더 알림' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('switch', { name: '저녁 리마인더 알림' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getAllByRole('switch')).toHaveLength(4);
  });

  it('토글 클릭 → 행 단위 즉시 update 호출', () => {
    const state = baseState();
    stateMock.mockReturnValue(state);
    renderWithIntl(<NotificationSettingsController />);

    fireEvent.click(screen.getByRole('switch', { name: '식단 완성 알림' }));
    expect(state.update).toHaveBeenCalledWith('mealplan_done', { enabled: false });

    fireEvent.click(screen.getByRole('switch', { name: '점심 리마인더 알림' }));
    expect(state.update).toHaveBeenCalledWith('meal_reminder_lunch', { enabled: true });
  });

  it('시각 변경 → localTime 저장, localTime null 이면 기본값(18:30) 표시', () => {
    const state = baseState();
    stateMock.mockReturnValue(state);
    renderWithIntl(<NotificationSettingsController />);

    const dinnerTime = screen.getByLabelText('저녁 알림 시각');
    expect(dinnerTime).toHaveValue('18:30');
    fireEvent.change(dinnerTime, { target: { value: '19:00' } });
    expect(state.update).toHaveBeenCalledWith('meal_reminder_dinner', { localTime: '19:00' });
  });

  it('꺼진 행의 시각 피커는 비활성, 저장 중 행은 토글 비활성', () => {
    stateMock.mockReturnValue(
      baseState({ savingTypes: new Set(['meal_reminder_breakfast']) }),
    );
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.getByLabelText('점심 알림 시각')).toBeDisabled();
    expect(screen.getByRole('switch', { name: '아침 리마인더 알림' })).toBeDisabled();
  });

  it('저장 실패 배너 + 닫기', () => {
    const state = baseState({ updateError: true });
    stateMock.mockReturnValue(state);
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.getByRole('alert')).toHaveTextContent('알림 설정 변경에 실패했어요');
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(state.dismissError).toHaveBeenCalledTimes(1);
  });

  it('헤더 뒤로가기 → /settings (9장 진입점 복귀)', () => {
    renderWithIntl(<NotificationSettingsController />);
    fireEvent.click(screen.getByRole('button', { name: '설정으로 돌아가기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/settings');
  });
});

describe('NotificationSettingsController — 앱/웹 분기 (ui-design 12장 ③④)', () => {
  it('웹 브라우저: "앱에서 받을 수 있어요" 안내 카드, 권한 배너 없음', () => {
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.getByText('푸시 알림은 앱에서 받을 수 있어요')).toBeInTheDocument();
    expect(screen.queryByText('기기 설정에서 알림을 켜 주세요')).not.toBeInTheDocument();
  });

  it('앱 내 + 권한 거부: 상단 배너 → OPEN_OS_SETTINGS 전송, 웹 안내 카드 없음', () => {
    app = stubAppEnvironment();
    useBridgeStore.setState({ permission: 'denied' });
    renderWithIntl(<NotificationSettingsController />);

    expect(screen.queryByText('푸시 알림은 앱에서 받을 수 있어요')).not.toBeInTheDocument();
    expect(screen.getByText('기기 설정에서 알림을 켜 주세요')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '설정 열기' }));
    expect(JSON.parse(app.postMessage.mock.calls[0]?.[0] as string)).toEqual({
      v: 1,
      type: 'OPEN_OS_SETTINGS',
      payload: {},
    });
  });

  it('앱 내 + 권한 granted: 배너 미노출', () => {
    app = stubAppEnvironment();
    useBridgeStore.setState({ permission: 'granted' });
    renderWithIntl(<NotificationSettingsController />);
    expect(screen.queryByText('기기 설정에서 알림을 켜 주세요')).not.toBeInTheDocument();
  });
});
