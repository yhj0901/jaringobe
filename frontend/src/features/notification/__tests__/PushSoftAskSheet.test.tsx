import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { act, renderHook } from '@testing-library/react';
import { PushSoftAskSheet, usePushSoftAsk } from '@/features/notification/PushSoftAskSheet';
import { PUSH_SOFT_ASK_SHOWN_KEY } from '@/features/notification/constants';
import { useBridgeStore } from '@/shared/bridge/store';
import { renderWithIntl } from '@/test/renderWithIntl';
import { stubAppEnvironment, type AppEnvStub } from '@/test/appEnv';

let app: AppEnvStub | null = null;

beforeEach(() => {
  window.localStorage.clear();
  useBridgeStore.getState().reset();
});

afterEach(() => {
  app?.restore();
  app = null;
});

describe('usePushSoftAsk (FR-002 — 앱 내·미결정·생성 직후 1회)', () => {
  it('앱 내 + undetermined → 1회 오픈, 이후 재요청은 무시', () => {
    app = stubAppEnvironment();
    useBridgeStore.setState({ permission: 'undetermined' });
    const { result } = renderHook(() => usePushSoftAsk());

    act(() => result.current.requestSoftAsk());
    expect(result.current.open).toBe(true);
    expect(window.localStorage.getItem(PUSH_SOFT_ASK_SHOWN_KEY)).toBe('1');

    act(() => result.current.decline());
    expect(result.current.open).toBe(false);

    // 거부 후 재노출 금지 (localStorage 마커)
    act(() => result.current.requestSoftAsk());
    expect(result.current.open).toBe(false);
  });

  it('수락 → REQUEST_PUSH_PERMISSION 전송 후 닫힘', () => {
    app = stubAppEnvironment();
    useBridgeStore.setState({ permission: 'undetermined' });
    const { result } = renderHook(() => usePushSoftAsk());

    act(() => result.current.requestSoftAsk());
    act(() => result.current.accept());

    expect(result.current.open).toBe(false);
    expect(JSON.parse(app.postMessage.mock.calls[0]?.[0] as string)).toEqual({
      v: 1,
      type: 'REQUEST_PUSH_PERMISSION',
      payload: {},
    });
  });

  it('앱 밖이거나 권한이 미결정이 아니면 열지 않는다', () => {
    // 앱 밖
    const web = renderHook(() => usePushSoftAsk());
    act(() => web.result.current.requestSoftAsk());
    expect(web.result.current.open).toBe(false);
    expect(window.localStorage.getItem(PUSH_SOFT_ASK_SHOWN_KEY)).toBeNull();

    // 앱 내 + granted
    app = stubAppEnvironment();
    useBridgeStore.setState({ permission: 'granted' });
    const granted = renderHook(() => usePushSoftAsk());
    act(() => granted.result.current.requestSoftAsk());
    expect(granted.result.current.open).toBe(false);

    // 앱 내 + denied — 재요청 없이 설정 화면 유도 (FR-002)
    useBridgeStore.setState({ permission: 'denied' });
    const denied = renderHook(() => usePushSoftAsk());
    act(() => denied.result.current.requestSoftAsk());
    expect(denied.result.current.open).toBe(false);
  });
});

describe('PushSoftAskSheet', () => {
  it('open 시 문구·버튼 렌더, [좋아요]/[나중에] 콜백 호출', () => {
    const onAccept = vi.fn();
    const onDecline = vi.fn();
    renderWithIntl(<PushSoftAskSheet open onAccept={onAccept} onDecline={onDecline} />);

    expect(screen.getByText('완성되면 알려드릴까요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '좋아요' }));
    expect(onAccept).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '나중에' }));
    expect(onDecline).toHaveBeenCalledTimes(1);
  });

  it('open=false 면 렌더하지 않는다', () => {
    renderWithIntl(<PushSoftAskSheet open={false} onAccept={vi.fn()} onDecline={vi.fn()} />);
    expect(screen.queryByText('완성되면 알려드릴까요?')).not.toBeInTheDocument();
  });
});
