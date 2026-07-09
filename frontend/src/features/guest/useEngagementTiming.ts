'use client';

import { useEffect, useRef } from 'react';
import {
  PROMPT_DWELL_MS,
  PROMPT_SHOWN_SESSION_KEY,
  PROMPT_TICK_MS,
  SCROLL_IDLE_MS,
} from '@/shared/config/constants';

interface EngagementTimingOptions {
  enabled: boolean;
  onTrigger: () => void;
}

/**
 * 타이밍 프롬프트 감지 (FR-102)
 * - 가시 상태(document.visibilityState === 'visible') 누적 체류 10초
 * - 스크롤 유휴 1.5초 (스크롤 조작 중 노출 금지)
 * - 세션 내 미노출(sessionStorage) 일 때만 1회 트리거
 */
export function useEngagementTiming({ enabled, onTrigger }: EngagementTimingOptions): void {
  const onTriggerRef = useRef(onTrigger);
  onTriggerRef.current = onTrigger;

  useEffect(() => {
    if (!enabled) return undefined;
    if (window.sessionStorage.getItem(PROMPT_SHOWN_SESSION_KEY) !== null) return undefined;

    let dwellMs = 0;
    let lastScrollAt = 0;

    const handleScroll = () => {
      lastScrollAt = Date.now();
    };
    window.addEventListener('scroll', handleScroll, { passive: true });

    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        dwellMs += PROMPT_TICK_MS;
      }
      const scrollIdle = Date.now() - lastScrollAt >= SCROLL_IDLE_MS;
      if (dwellMs >= PROMPT_DWELL_MS && scrollIdle) {
        window.clearInterval(interval);
        window.removeEventListener('scroll', handleScroll);
        window.sessionStorage.setItem(PROMPT_SHOWN_SESSION_KEY, '1');
        onTriggerRef.current();
      }
    }, PROMPT_TICK_MS);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener('scroll', handleScroll);
    };
  }, [enabled]);
}
