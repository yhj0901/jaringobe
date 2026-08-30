'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { BottomSheet } from '@/shared/ui/BottomSheet';
import { isApp, sendToApp, BRIDGE_VERSION } from '@/shared/bridge';
import { useBridgeStore } from '@/shared/bridge/store';
import { PUSH_SOFT_ASK_SHOWN_KEY } from '@/features/notification/constants';

/**
 * 푸시 권한 soft ask (ui-design 12장, FR-002)
 * 앱 내 + 권한 미결정(undetermined) + 식단 생성 요청 직후 1회 —
 * 수락 시 REQUEST_PUSH_PERMISSION, 거부 후엔 재노출 없이 알림 설정 화면에서만 유도.
 */
export interface PushSoftAskState {
  open: boolean;
  /** 식단 생성 요청 직후 호출 — 조건 충족 시 1회 오픈 */
  requestSoftAsk: () => void;
  accept: () => void;
  decline: () => void;
}

export function usePushSoftAsk(): PushSoftAskState {
  const [open, setOpen] = useState(false);

  const requestSoftAsk = useCallback(() => {
    if (!isApp()) return;
    if (useBridgeStore.getState().permission !== 'undetermined') return;
    if (window.localStorage.getItem(PUSH_SOFT_ASK_SHOWN_KEY) === '1') return; // 1회 한정
    window.localStorage.setItem(PUSH_SOFT_ASK_SHOWN_KEY, '1');
    setOpen(true);
  }, []);

  const accept = useCallback(() => {
    sendToApp({ v: BRIDGE_VERSION, type: 'REQUEST_PUSH_PERMISSION', payload: {} });
    setOpen(false);
  }, []);

  const decline = useCallback(() => setOpen(false), []);

  return { open, requestSoftAsk, accept, decline };
}

interface PushSoftAskSheetProps {
  open: boolean;
  onAccept: () => void;
  onDecline: () => void;
}

/** soft ask 바텀시트 — "완성되면 알려드릴까요?" [좋아요/나중에] */
export function PushSoftAskSheet({ open, onAccept, onDecline }: PushSoftAskSheetProps) {
  const t = useTranslations('notification.softAsk');

  return (
    <BottomSheet open={open} onClose={onDecline} labelledBy="push-soft-ask-title">
      <h2 id="push-soft-ask-title" className="text-lg font-extrabold tracking-tight text-navy-900">
        {t('title')}
      </h2>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-500">{t('description')}</p>
      <div className="mt-5 flex gap-2.5">
        <button
          type="button"
          onClick={onDecline}
          className="flex-1 rounded-2xl bg-[#F0F2F6] px-4 py-3.5 text-sm font-bold text-ink-500"
        >
          {t('later')}
        </button>
        <button
          type="button"
          onClick={onAccept}
          className="flex-1 rounded-2xl bg-brand-600 px-4 py-3.5 text-sm font-extrabold text-white shadow-cta"
        >
          {t('accept')}
        </button>
      </div>
    </BottomSheet>
  );
}
