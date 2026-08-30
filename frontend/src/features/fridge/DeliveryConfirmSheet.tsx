'use client';

import { useTranslations } from 'next-intl';

interface DeliveryConfirmSheetProps {
  busy: boolean;
  onYes: () => void;
  onAdjust: () => void;
  onNotYet: () => void;
}

/** 배송 ETA 자동등록 뒤 실제 도착 여부를 확인하는 보정 진입점 (ui-design 14-4). */
export function DeliveryConfirmSheet({
  busy,
  onYes,
  onAdjust,
  onNotYet,
}: DeliveryConfirmSheetProps) {
  const t = useTranslations('fridge.delivery');
  return (
    <section aria-label={t('title')} className="rounded-[20px] border border-brand-100 bg-white p-4 shadow-card">
      <h2 className="text-[15px] font-extrabold text-navy-900">{t('title')}</h2>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-500">{t('body')}</p>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" disabled={busy} onClick={onYes} className="rounded-xl bg-brand-600 px-3 py-2.5 text-xs font-extrabold text-white disabled:opacity-50">
          {t('yes')}
        </button>
        <button type="button" disabled={busy} onClick={onAdjust} className="rounded-xl bg-[#F0F2F6] px-3 py-2.5 text-xs font-extrabold text-ink-600 disabled:opacity-50">
          {t('adjust')}
        </button>
        <button type="button" disabled={busy} onClick={onNotYet} className="col-span-2 rounded-xl border border-flame-200 px-3 py-2.5 text-xs font-extrabold text-flame-500 disabled:opacity-50">
          {t('notYet')}
        </button>
      </div>
    </section>
  );
}
