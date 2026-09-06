'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/routing';
import {
  addFridgeItems,
  daysUntil,
  deleteFridgeItem,
  listFridge,
  updateFridgeQuantity,
  type FridgeItem,
} from '@/features/fridge/api';
import { DeliveryConfirmSheet } from '@/features/fridge/DeliveryConfirmSheet';
import { fetchCycle } from '@/features/cycle/api';
import { confirmOrderDelivery, fetchLatestOrder } from '@/features/order/api';
import type { OrderResponse } from '@/features/order/types';

const EXPIRY_SOON_DAYS = 3;
const EMPTY_FORM = { name: '', quantity: '', unit: 'ea', expiresAt: '' };
const DELIVERY_CONFIRMED_PREFIX = 'fridge.delivery.confirmed:';

/**
 * 수동 가상 냉장고 — 실제 백엔드 fridge API 연동 (목록/추가/삭제).
 * 배송 자동등록(order 연동)·식사완료 자동차감은 후속. 지금은 수동 관리.
 */
export function FridgeManager() {
  const t = useTranslations('fridgePage');
  const tDelivery = useTranslations('fridge.delivery');
  const tExpiring = useTranslations('fridge.expiring');
  const [items, setItems] = useState<FridgeItem[]>([]);
  const [state, setState] = useState<'loading' | 'ready' | 'auth' | 'error'>('loading');
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [deliveryOrder, setDeliveryOrder] = useState<OrderResponse | null>(null);
  const [deliverySheetOpen, setDeliverySheetOpen] = useState(false);
  const [deliveryBusy, setDeliveryBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editingQuantities, setEditingQuantities] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [res, latest, cycle] = await Promise.all([
      listFridge(),
      fetchLatestOrder(),
      fetchCycle(),
    ]);
    if (res.ok) {
      setItems(res.data);
      setState('ready');
    } else {
      setState(res.status === 401 ? 'auth' : 'error');
    }
    if (latest.ok && latest.data.status === 'confirmed') {
      setDeliveryOrder(latest.data);
      setDeliverySheetOpen(
        window.localStorage.getItem(`${DELIVERY_CONFIRMED_PREFIX}${latest.data.id}`) !== '1' &&
        latest.data.deliveryState !== 'unknown' &&
          (latest.data.inboundAt !== null ||
            latest.data.deliveryState === 'delivered' ||
            (cycle.ok && cycle.data.stage === 'delivered')),
      );
    } else {
      setDeliveryOrder(null);
      setDeliverySheetOpen(false);
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

  const onAdjust = () => {
    setEditingQuantities(Object.fromEntries(items.map((item) => [item.id, item.quantity])));
    setEditing(true);
    setDeliverySheetOpen(false);
  };

  const onQuantitySave = async (item: FridgeItem) => {
    const quantity = editingQuantities[item.id]?.trim();
    if (!quantity || Number(quantity) <= 0) return;
    setSaving(true);
    const result = await updateFridgeQuantity(item.id, quantity);
    setSaving(false);
    if (result.ok) {
      setItems((current) => current.map((candidate) => (candidate.id === item.id ? result.data : candidate)));
    }
  };

  const onDelivery = async (received: boolean) => {
    if (deliveryOrder === null || deliveryBusy) return;
    setDeliveryBusy(true);
    const result = await confirmOrderDelivery(deliveryOrder.id, received);
    setDeliveryBusy(false);
    if (!result.ok) return;
    if (received) {
      window.localStorage.setItem(`${DELIVERY_CONFIRMED_PREFIX}${deliveryOrder.id}`, '1');
    }
    setDeliveryOrder(result.data);
    setDeliverySheetOpen(false);
    await load();
  };

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-4">
      <header>
        <Link
          href="/"
          aria-label={t('back')}
          className="mb-2 inline-flex items-center gap-1 text-[13px] font-bold text-ink-300 hover:text-navy-900"
        >
          <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M15 5l-7 7 7 7"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          {t('back')}
        </Link>
        <h1 className="text-lg font-extrabold text-navy-900">{t('title')}</h1>
        <p className="mt-1 text-[13px] text-ink-300">{t('subtitle')}</p>
      </header>

      {deliverySheetOpen ? (
        <DeliveryConfirmSheet
          busy={deliveryBusy}
          onYes={() => void onDelivery(true)}
          onAdjust={onAdjust}
          onNotYet={() => void onDelivery(false)}
        />
      ) : null}
      {deliveryOrder?.deliveryState === 'unknown' ? (
        <p role="status" className="rounded-xl bg-brand-50 px-3 py-2 text-xs font-bold text-brand-700">
          {tDelivery('unknownBanner')}
        </p>
      ) : null}

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
          <p className="py-6 text-center text-sm text-ink-300">{t('loading')}</p>
        ) : state === 'auth' ? (
          <p className="py-6 text-center text-sm text-ink-300">{t('loginRequired')}</p>
        ) : state === 'error' ? (
          <p className="py-6 text-center text-sm text-flame-500">{t('loadError')}</p>
        ) : items.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-300">{t('empty')}</p>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-ink-50">
              {items.map((item) => {
                const d = daysUntil(item.expiresAt);
                const soon = d !== null && d <= EXPIRY_SOON_DAYS;
                return (
                  <li key={item.id} className="flex flex-col gap-2 py-2.5">
                    <div className="flex items-center justify-between">
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
                    </div>
                    {editing ? (
                      <div className="flex gap-2">
                        <input
                          aria-label={t('editQuantityLabel', { name: item.name })}
                          inputMode="decimal"
                          value={editingQuantities[item.id] ?? item.quantity}
                          onChange={(event) =>
                            setEditingQuantities((current) => ({
                              ...current,
                              [item.id]: event.target.value,
                            }))
                          }
                          className="min-w-0 flex-1 rounded-[9px] border border-ink-100 px-3 py-2 text-sm"
                        />
                        <button
                          type="button"
                          disabled={saving}
                          onClick={() => void onQuantitySave(item)}
                          className="rounded-[9px] bg-navy-900 px-3 py-2 text-xs font-bold text-white disabled:opacity-40"
                        >
                          {t('saveQuantity')}
                        </button>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            {items.some((item) => {
              const d = daysUntil(item.expiresAt);
              return d !== null && d <= EXPIRY_SOON_DAYS;
            }) ? (
              <p className="mt-3 rounded-xl bg-flame-50 px-3 py-2 text-xs font-semibold text-ink-600">
                {tExpiring('nextPlanHint')}
              </p>
            ) : null}
          </>
        )}
      </section>
    </main>
  );
}
