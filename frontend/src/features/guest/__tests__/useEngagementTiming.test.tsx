import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useEngagementTiming } from '@/features/guest/useEngagementTiming';
import {
  PROMPT_DWELL_MS,
  PROMPT_SHOWN_SESSION_KEY,
  SCROLL_IDLE_MS,
} from '@/shared/config/constants';

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  });
}

describe('useEngagementTiming (FR-102)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setVisibility('visible');
  });

  afterEach(() => {
    vi.useRealTimers();
    setVisibility('visible');
  });

  it('가시 체류 10초 + 스크롤 유휴면 1회 트리거하고 세션 플래그를 기록한다', () => {
    const onTrigger = vi.fn();
    renderHook(() => useEngagementTiming({ enabled: true, onTrigger }));

    act(() => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS - 500);
    });
    expect(onTrigger).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(onTrigger).toHaveBeenCalledTimes(1);
    expect(window.sessionStorage.getItem(PROMPT_SHOWN_SESSION_KEY)).toBe('1');

    // 트리거 후 타이머가 정리되어 재호출 없음
    act(() => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS * 2);
    });
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });

  it('스크롤 조작 중에는 노출하지 않고 유휴 1.5초 후 트리거한다', () => {
    const onTrigger = vi.fn();
    renderHook(() => useEngagementTiming({ enabled: true, onTrigger }));

    // 12초 동안 0.5초마다 스크롤 → 유휴 조건 미충족
    act(() => {
      for (let i = 0; i < 24; i += 1) {
        window.dispatchEvent(new Event('scroll'));
        vi.advanceTimersByTime(500);
      }
    });
    expect(onTrigger).not.toHaveBeenCalled();

    // 스크롤 멈춤 → 유휴 1.5초 경과 시 트리거
    act(() => {
      vi.advanceTimersByTime(SCROLL_IDLE_MS + 300);
    });
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });

  it('숨김(hidden) 상태의 시간은 체류로 누적하지 않는다', () => {
    const onTrigger = vi.fn();
    renderHook(() => useEngagementTiming({ enabled: true, onTrigger }));

    act(() => {
      vi.advanceTimersByTime(5_000);
    });
    setVisibility('hidden');
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(onTrigger).not.toHaveBeenCalled();

    setVisibility('visible');
    act(() => {
      vi.advanceTimersByTime(5_500);
    });
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });

  it('세션 내 이미 노출된 경우 다시 트리거하지 않는다', () => {
    window.sessionStorage.setItem(PROMPT_SHOWN_SESSION_KEY, '1');
    const onTrigger = vi.fn();
    renderHook(() => useEngagementTiming({ enabled: true, onTrigger }));
    act(() => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS * 3);
    });
    expect(onTrigger).not.toHaveBeenCalled();
  });

  it('enabled=false 이면 동작하지 않는다', () => {
    const onTrigger = vi.fn();
    renderHook(() => useEngagementTiming({ enabled: false, onTrigger }));
    act(() => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS * 2);
    });
    expect(onTrigger).not.toHaveBeenCalled();
  });

  it('언마운트 시 타이머를 정리한다', () => {
    const onTrigger = vi.fn();
    const { unmount } = renderHook(() => useEngagementTiming({ enabled: true, onTrigger }));
    unmount();
    act(() => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS * 2);
    });
    expect(onTrigger).not.toHaveBeenCalled();
  });
});
