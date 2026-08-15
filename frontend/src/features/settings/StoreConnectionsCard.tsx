'use client';

import { useTranslations } from 'next-intl';
import { STORE_BRAND_COLORS } from '@/features/store/constants';
import type { StoreId } from '@/features/store/types';

interface StoreConnectionsCardProps {
  connections: Partial<Record<StoreId, boolean>>;
  /** user.country 의 스토어 노출 순서 (KR 4종 / US 2종, FR-603) */
  storeIds: StoreId[];
  /** 연동됨 항목의 서비스 계정 이메일 표시 (users/me.email — 프로토타입 accountLabel) */
  email: string | null;
  busyStore: StoreId | null;
  onToggle: (store: StoreId, nextConnected: boolean) => void;
}

/**
 * 자동 주문 연동 스토어 (FR-404/603, 프로토타입 settings stores 재현)
 * 국가별 스토어 브랜드 배지 + 연동됨(그린 라벨·해제)/연동하기(브랜드색 버튼). 확인 시트는 호출측.
 */
export function StoreConnectionsCard({
  connections,
  storeIds,
  email,
  busyStore,
  onToggle,
}: StoreConnectionsCardProps) {
  const t = useTranslations('settings.stores');
  const tStore = useTranslations('store');

  return (
    <section aria-label={t('section')} className="mt-[22px]">
      <h2 className="mx-0.5 mb-1 text-xs font-extrabold tracking-wide text-ink-400">
        {t('section')}
      </h2>
      <p className="mx-0.5 mb-2.5 text-xs leading-relaxed text-ink-300">{t('sub')}</p>
      <ul className="rounded-[18px] bg-white px-4 py-1.5 shadow-card">
        {storeIds.map((store, index) => {
          const connected = connections[store];
          const color = STORE_BRAND_COLORS[store];
          const name = tStore(`${store}.name`);
          return (
            <li
              key={store}
              className={`flex items-center gap-3 py-[13px] ${
                index < storeIds.length - 1 ? 'border-b border-[#F1F3F8]' : ''
              }`}
            >
              <span
                aria-hidden
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px] text-sm font-extrabold text-white"
                style={{ backgroundColor: color }}
              >
                {tStore(`${store}.mono`)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14.5px] font-bold text-ink-800">{name}</p>
                {connected ? (
                  <p className="mt-px truncate text-[11.5px] text-ink-300">
                    {email !== null ? `${t('linkedAccount')} · ${email}` : t('linkedAccount')}
                  </p>
                ) : null}
              </div>
              {connected ? (
                <span className="shrink-0 text-[11px] font-extrabold text-mint-600">
                  {t('connected')}
                </span>
              ) : null}
              <button
                type="button"
                disabled={busyStore === store}
                aria-label={connected ? t('disconnectLabel', { store: name }) : t('connectLabel', { store: name })}
                onClick={() => onToggle(store, !connected)}
                className={`shrink-0 rounded-[10px] px-3.5 py-[7px] text-xs disabled:opacity-60 ${
                  connected ? 'bg-[#F0F2F6] font-bold text-ink-400' : 'font-extrabold text-white'
                }`}
                style={connected ? undefined : { backgroundColor: color }}
              >
                {connected ? t('disconnect') : t('connect')}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
