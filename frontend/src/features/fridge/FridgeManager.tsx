'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  addFridgeItems,
  daysUntil,
  deleteFridgeItem,
  listFridge,
  type FridgeItem,
} from '@/features/fridge/api';

const EXPIRY_SOON_DAYS = 3;
const EMPTY_FORM = { name: '', quantity: '', unit: 'ea', expiresAt: '' };

/**
 * 수동 가상 냉장고 — 실제 백엔드 fridge API 연동 (목록/추가/삭제).
 * 배송 자동등록(order 연동)·식사완료 자동차감은 후속. 지금은 수동 관리.
 */
export function FridgeManager() {
  const t = useTranslations('fridgePage');
  const [items, setItems] = useState<FridgeItem[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'auth' | 'error'>('loading');
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const res = await listFridge();
    if (res.ok) {
      setItems(res.data);
      setState('ready');
    } else {
      setState(res.status === 401 ? 'auth' : 'error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.quantity.trim() || saving) return;
    setSaving(true);
    const res = await addFridgeItems([
      {
        name: form.name.trim(),
        quantity: form.quantity.trim(),
        unit: form.unit.trim() || 'ea',
        expiresAt: form.expiresAt || null,
        source: 'manual',
      },
    ]);
    setSaving(false);
    if (res.ok) {
      setForm(EMPTY_FORM);
      await load();
    }
  };

  const onDelete = async (id: string) => {
    const res = await deleteFridgeItem(id);
    if (res.ok) await load();
  };

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-4">
      <header>
        <h1 className="text-lg font-extrabold text-navy-900">{t('title')}</h1>
        <p className="mt-1 text-[13px] text-ink-300">{t('subtitle')}</p>
      </header>

      {/* 추가 폼 */}
      <form
        onSubmit={onAdd}
        className="rounded-[20px] border border-ink-100 bg-white p-4 shadow-card"
      >
        <h2 className="mb-2.5 text-[14px] font-bold text-navy-900">{t('addTitle')}</h2>
        <div className="flex flex-col gap-2">
          <input
            className="rounded-[9px] border border-ink-100 px-3 py-2 text-sm"
            placeholder={t('name')}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            maxLength={200}
          />
          <div className="flex gap-2">
            <input
              className="w-1/2 rounded-[9px] border border-ink-100 px-3 py-2 text-sm"
              placeholder={t('quantity')}
              inputMode="decimal"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            />
            <input
              className="w-1/2 rounded-[9px] border border-ink-100 px-3 py-2 text-sm"
              placeholder={t('unit')}
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              maxLength={16}
            />
          </div>
          <input
            type="date"
            className="rounded-[9px] border border-ink-100 px-3 py-2 text-sm text-ink-800"
            aria-label={t('expiresAt')}
            value={form.expiresAt}
            onChange={(e) => setForm({ ...form, expiresAt: e.target.value })}
          />
          <button
            type="submit"
            disabled={saving || !form.name.trim() || !form.quantity.trim()}
            className="rounded-[10px] bg-navy-900 py-2.5 text-sm font-bold text-white disabled:opacity-40"
          >
            {t('addButton')}
          </button>
        </div>
      </form>

      {/* 목록 */}
      <section
        aria-label={t('title')}
        className="rounded-[20px] border border-ink-100 bg-white p-4 shadow-card"
      >
        {state === 'loading' ? (
          <p className="py-6 text-center text-sm text-ink-300">…</p>
        ) : state === 'auth' ? (
          <p className="py-6 text-center text-sm text-ink-300">{t('loginRequired')}</p>
        ) : state === 'error' ? (
          <p className="py-6 text-center text-sm text-flame-500">{t('loadError')}</p>
        ) : items.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-300">{t('empty')}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-ink-50">
            {items.map((item) => {
              const d = daysUntil(item.expiresAt);
              const soon = d !== null && d <= EXPIRY_SOON_DAYS;
              return (
                <li key={item.id} className="flex items-center justify-between py-2.5">
                  <span className="text-[13.5px] font-semibold text-ink-800">
                    {item.name}
                    <span className="ml-1.5 text-xs font-medium text-ink-300">
                      {item.quantity}
                      {item.unit}
                    </span>
                  </span>
                  <span className="flex items-center gap-2.5">
                    {d !== null ? (
                      <span
                        className={`text-xs font-extrabold tabular-nums ${
                          soon ? 'text-flame-500' : 'text-ink-300'
                        }`}
                      >
                        {d < 0 ? t('expired') : t('expiresIn', { days: d })}
                      </span>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => void onDelete(item.id)}
                      aria-label={t('deleteLabel', { name: item.name })}
                      className="text-xs font-bold text-ink-300 hover:text-flame-500"
                    >
                      ✕
                    </button>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </main>
  );
}
