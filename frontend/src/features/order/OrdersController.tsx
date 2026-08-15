'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Link, useRouter } from '@/i18n/routing';
import { Badge } from '@/shared/ui/Badge';
import { MoneyText } from '@/shared/ui/MoneyText';
import { createOrder, fetchLatestOrder, fetchOrderPreview } from '@/features/order/api';
import { pickFirstConnectedStore } from '@/features/order/pickStore';
import {
  MEALPLAN_NOT_FOUND_CODE,
  ORDER_NOT_FOUND_CODE,
  type OrderCartItem,
  type OrderItem,
  type OrderPreviewLine,
  type OrderPreviewResponse,
  type OrderResponse,
} from '@/features/order/types';
import { fetchStoreConnections } from '@/features/store/api';
import type { StoreConnection, StoreId } from '@/features/store/types';

const ORDER_ERROR_CODES = [
  'STORE_NOT_CONNECTED',
  'NOTHING_TO_ORDER',
  'MEALPLAN_NOT_FOUND',
  'ORDER_NOT_FOUND',
  'RATE_LIMITED',
  'STORE_NOT_SUPPORTED',
  'VALIDATION_ERROR',
  'AUTH_REQUIRED',
] as const;

type PageStatus = 'loading' | 'unauthenticated' | 'error' | 'no-plan' | 'ready';

function cartItemFor(name: string, items: OrderCartItem[]): OrderCartItem | undefined {
  const key = name.trim().toLowerCase();
  return items.find((item) => item.ingredient.trim().toLowerCase() === key);
}

function formatSuggestedDate(iso: string, locale: string): string {
  const tag = locale === 'en' ? 'en-US' : 'ko-KR';
  return new Intl.DateTimeFormat(tag, { year: 'numeric', month: 'long', day: 'numeric' }).format(
    new Date(iso),
  );
}

/**
 * 장바구니 리뷰 (`/orders`) — needed vs covered, 시뮬레이션 확정, fridge inbound 안내 (ui-design 13장).
 * POST body 는 `{ store }` 만. 홈 진입·preview 조회로 주문을 만들지 않음.
 */
export function OrdersController() {
  const t = useTranslations('orders');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const router = useRouter();

  const [status, setStatus] = useState<PageStatus>('loading');
  const [preview, setPreview] = useState<OrderPreviewResponse | null>(null);
  const [connections, setConnections] = useState<StoreConnection[]>([]);
  const [latest, setLatest] = useState<OrderResponse | null>(null);
  const [confirmed, setConfirmed] = useState<OrderResponse | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus('loading');
    setErrorCode(null);
    setConfirmed(null);
    const [previewRes, storesRes, latestRes] = await Promise.all([
      fetchOrderPreview(),
      fetchStoreConnections(),
      fetchLatestOrder(),
    ]);

    if (
      (!previewRes.ok && previewRes.status === 401) ||
      (!storesRes.ok && storesRes.status === 401)
    ) {
      setStatus('unauthenticated');
      return;
    }

    const nextConnections = storesRes.ok ? storesRes.data.connections : [];
    const nextLatest = latestRes.ok ? latestRes.data : null;

    if (!previewRes.ok && previewRes.code === MEALPLAN_NOT_FOUND_CODE) {
      setPreview(null);
      setConnections(nextConnections);
      setLatest(nextLatest);
      setStatus('no-plan');
      return;
    }

    if (!previewRes.ok) {
      setStatus('error');
      return;
    }

    setPreview(previewRes.data);
    setConnections(nextConnections);
    setLatest(nextLatest);
    setStatus('ready');
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.replace('/login?next=/orders');
    }
  }, [status, router]);

  const store: StoreId | null = useMemo(() => {
    if (preview === null) return pickFirstConnectedStore('KR', connections);
    return pickFirstConnectedStore(preview.country, connections);
  }, [preview, connections]);

  const errorMessage = (code: string): string => {
    if ((ORDER_ERROR_CODES as readonly string[]).includes(code)) {
      return t(`error.${code}`);
    }
    return tCommon('error.fallback');
  };

  const handleConfirm = async () => {
    if (store === null || confirming || preview === null || preview.needed.length === 0) return;
    setConfirming(true);
    setErrorCode(null);
    const result = await createOrder({ store });
    setConfirming(false);
    if (result.ok) {
      setConfirmed(result.data);
      setLatest(result.data);
      return;
    }
    setErrorCode(result.code);
  };

  if (status === 'loading' || status === 'unauthenticated') {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label={t('loading')}
        className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col gap-3.5 bg-surface-app px-[18px] pb-6 pt-8 sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card"
      >
        <div aria-hidden className="h-[48px] animate-pulse rounded-[14px] bg-white shadow-card" />
        <div aria-hidden className="h-[180px] animate-pulse rounded-[20px] bg-white shadow-card" />
        <div aria-hidden className="h-[120px] animate-pulse rounded-[20px] bg-white shadow-card" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col bg-surface-app sm:min-h-0 sm:my-6 sm:overflow-hidden sm:rounded-[32px] sm:shadow-card">
      <header className="flex items-center gap-3 border-b border-[#EEF1F6] bg-white px-[18px] pb-3.5 pt-8">
        <Link
          href="/"
          aria-label={t('backLabel')}
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-surface-app"
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
        </Link>
        <h1 className="text-[17px] font-extrabold text-navy-900">{t('title')}</h1>
      </header>

      <main className="flex flex-1 flex-col gap-3.5 px-[18px] py-4">
        {status === 'error' ? (
          <ErrorPanel message={t('loadFailed')} onRetry={() => void load()} retryLabel={t('retry')} />
        ) : null}

        {status === 'no-plan' ? (
          <section className="rounded-[20px] bg-white p-5 shadow-card">
            <h2 className="text-[15px] font-extrabold text-navy-900">{t('emptyMealplan.title')}</h2>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-500">
              {t('emptyMealplan.description')}
            </p>
            <button
              type="button"
              onClick={() => router.push('/')}
              className="mt-4 w-full rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta"
            >
              {t('emptyMealplan.cta')}
            </button>
          </section>
        ) : null}

        {confirmed !== null ? (
          <ConfirmedSnapshot order={confirmed} locale={locale} />
        ) : null}

        {status === 'ready' && preview !== null && confirmed === null ? (
          <ReviewBody
            preview={preview}
            locale={locale}
            store={store}
            hasLatest={latest !== null}
            confirming={confirming}
            errorCode={errorCode}
            errorMessage={errorCode ? errorMessage(errorCode) : null}
            onConfirm={() => void handleConfirm()}
            onRetry={() => void load()}
            onDismissError={() => setErrorCode(null)}
            onSettings={() => router.push('/settings')}
          />
        ) : null}
      </main>
    </div>
  );
}

function ErrorPanel({
  message,
  onRetry,
  retryLabel,
}: {
  message: string;
  onRetry: () => void;
  retryLabel: string;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-[16px] border border-flame-200 bg-white p-4 shadow-card"
    >
      <p className="text-[13px] font-semibold text-ink-600">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="self-start rounded-[12px] bg-brand-600 px-4 py-2 text-xs font-extrabold text-white"
      >
        {retryLabel}
      </button>
    </div>
  );
}

function ReviewBody({
  preview,
  locale,
  store,
  hasLatest,
  confirming,
  errorCode,
  errorMessage,
  onConfirm,
  onRetry,
  onDismissError,
  onSettings,
}: {
  preview: OrderPreviewResponse;
  locale: string;
  store: StoreId | null;
  hasLatest: boolean;
  confirming: boolean;
  errorCode: string | null;
  errorMessage: string | null;
  onConfirm: () => void;
  onRetry: () => void;
  onDismissError: () => void;
  onSettings: () => void;
}) {
  const t = useTranslations('orders');
  const neededEmpty = preview.needed.length === 0;
  const confirmDisabled = neededEmpty || store === null || confirming;
  const showNoStore = store === null || errorCode === 'STORE_NOT_CONNECTED';

  return (
    <>
      {errorMessage && errorCode !== 'STORE_NOT_CONNECTED' ? (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-2xl border border-flame-200 bg-white p-4 shadow-card"
        >
          <p className="text-[13px] font-semibold text-ink-600">{errorMessage}</p>
          <div className="flex shrink-0 gap-1.5">
            <button
              type="button"
              onClick={onRetry}
              className="rounded-[10px] bg-brand-600 px-3 py-1.5 text-xs font-extrabold text-white"
            >
              {t('retry')}
            </button>
            <button
              type="button"
              onClick={onDismissError}
              className="rounded-[10px] bg-[#F0F2F6] px-3 py-1.5 text-xs font-bold text-ink-500"
            >
              {t('dismiss')}
            </button>
          </div>
        </div>
      ) : null}

      {showNoStore ? (
        <div
          role="alert"
          className="rounded-[16px] border border-flame-200 bg-white p-4 shadow-card"
        >
          <p className="text-[13px] font-extrabold text-navy-900">{t('noStore.title')}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-ink-500">
            {t('noStore.description')}
          </p>
          <button
            type="button"
            onClick={onSettings}
            className="mt-3 w-full rounded-[12px] bg-brand-600 px-4 py-2.5 text-sm font-extrabold text-white shadow-cta"
          >
            {t('noStore.cta')}
          </button>
        </div>
      ) : null}

      <LineSection
        title={t('needed.title')}
        emptyLabel={neededEmpty ? t('nothingToOrder') : undefined}
        lines={preview.needed}
        cartItems={preview.cart.items}
        locale={locale}
        kind="needed"
      />

      {preview.covered.length > 0 ? (
        <LineSection
          title={t('covered.title')}
          lines={preview.covered}
          cartItems={preview.cart.items}
          locale={locale}
          kind="covered"
        />
      ) : null}

      <section className="rounded-[20px] bg-white p-4 shadow-card">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[13px] font-bold text-ink-500">{t('estimateTotal')}</span>
          <MoneyText
            money={preview.estimatedTotal}
            locale={locale}
            className="text-[16px] font-extrabold text-navy-900"
          />
        </div>
        {preview.country === 'KR' ? (
          <p className="mt-1.5 text-[11.5px] text-ink-400">{t('estimateSource')}</p>
        ) : null}
        {/* 고지 — 색만으로 구분하지 않음 (일반 텍스트, 버튼 근처) */}
        <p className="mt-3 text-[12.5px] font-semibold leading-relaxed text-ink-600">
          {t('simulationNotice')}
        </p>
        {hasLatest ? (
          <p className="mt-2 text-[12px] leading-relaxed text-ink-500">{t('reconfirmWarning')}</p>
        ) : null}
        <button
          type="button"
          disabled={confirmDisabled}
          onClick={onConfirm}
          className="mt-3 w-full rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta disabled:opacity-40"
        >
          {confirming ? t('confirming') : t('confirmCta')}
        </button>
      </section>
    </>
  );
}

function LineSection({
  title,
  emptyLabel,
  lines,
  cartItems,
  locale,
  kind,
}: {
  title: string;
  emptyLabel?: string;
  lines: OrderPreviewLine[];
  cartItems: OrderCartItem[];
  locale: string;
  kind: 'needed' | 'covered';
}) {
  const t = useTranslations('orders');
  return (
    <section className="rounded-[20px] bg-white p-4 shadow-card">
      <h2 className="mb-2.5 text-[14.5px] font-extrabold text-navy-900">{title}</h2>
      {emptyLabel && lines.length === 0 ? (
        <p className="py-2 text-[13px] text-ink-400">{emptyLabel}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-ink-50">
          {lines.map((line) => {
            const matched = kind === 'needed' ? cartItemFor(line.name, cartItems) : undefined;
            const qty = kind === 'needed' ? line.toBuy : line.fromFridge;
            return (
              <li key={`${line.name}-${line.unit}`} className="flex flex-col gap-0.5 py-2.5">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[13.5px] font-semibold text-ink-800">{line.name}</span>
                  <span className="text-xs font-bold tabular-nums text-ink-400">
                    {kind === 'covered'
                      ? t('fromFridge', { qty, unit: line.unit })
                      : t('qty', { qty, unit: line.unit })}
                  </span>
                </div>
                {kind === 'needed' ? (
                  matched?.matched && matched.title ? (
                    <span className="flex items-baseline justify-between gap-2 text-[12px] text-ink-500">
                      <span className="truncate">{matched.title}</span>
                      {matched.price ? (
                        <MoneyText money={matched.price} locale={locale} className="shrink-0 font-bold" />
                      ) : null}
                    </span>
                  ) : (
                    <span className="text-[12px] text-ink-300">{t('noPrice')}</span>
                  )
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function ConfirmedSnapshot({ order, locale }: { order: OrderResponse; locale: string }) {
  const t = useTranslations('orders');
  const needed = order.items.filter((item) => item.lineType === 'needed');
  const covered = order.items.filter((item) => item.lineType === 'covered');
  const dateLabel = formatSuggestedDate(order.nextSuggestedAt, locale);

  return (
    <section className="rounded-[20px] bg-white p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="flex-1 text-[14.5px] font-extrabold text-navy-900">{t('title')}</h2>
        <Badge tone="brand">{t('confirmedBadge')}</Badge>
      </div>
      <p className="text-[12.5px] font-semibold leading-relaxed text-ink-600">
        {t('simulationNotice')}
      </p>
      <p role="status" aria-live="polite" className="mt-3 text-[13px] font-bold text-mint-700">
        {t('fridgeInbound')}
      </p>
      <p role="status" aria-live="polite" className="mt-1 text-[12.5px] text-ink-500">
        {t('nextSuggested', { date: dateLabel })}
      </p>
      <SnapshotList title={t('needed.title')} items={needed} locale={locale} />
      {covered.length > 0 ? (
        <SnapshotList title={t('covered.title')} items={covered} locale={locale} />
      ) : null}
      <div className="mt-3 flex items-center justify-between border-t border-ink-50 pt-3">
        <span className="text-[13px] font-bold text-ink-500">{t('estimateTotal')}</span>
        <MoneyText
          money={order.estimatedTotal}
          locale={locale}
          className="text-[16px] font-extrabold text-navy-900"
        />
      </div>
    </section>
  );
}

function SnapshotList({
  title,
  items,
  locale,
}: {
  title: string;
  items: OrderItem[];
  locale: string;
}) {
  const t = useTranslations('orders');
  return (
    <div className="mt-3">
      <h3 className="mb-1.5 text-xs font-bold text-ink-400">{title}</h3>
      <ul className="flex flex-col divide-y divide-ink-50">
        {items.map((item) => (
          <li key={`${item.lineType}-${item.name}-${item.unit}`} className="flex flex-col gap-0.5 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-semibold text-ink-800">{item.name}</span>
              <span className="text-xs font-bold tabular-nums text-ink-400">
                {t('qty', { qty: item.quantity, unit: item.unit })}
              </span>
            </div>
            {item.lineType === 'needed' ? (
              item.matched && item.title ? (
                <span className="flex items-baseline justify-between gap-2 text-[12px] text-ink-500">
                  <span className="truncate">{item.title}</span>
                  {item.unitPrice ? (
                    <MoneyText money={item.unitPrice} locale={locale} className="shrink-0 font-bold" />
                  ) : null}
                </span>
              ) : (
                <span className="text-[12px] text-ink-300">{t('noPrice')}</span>
              )
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
