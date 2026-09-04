'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Link, useRouter } from '@/i18n/routing';
import { Badge } from '@/shared/ui/Badge';
import { MoneyText } from '@/shared/ui/MoneyText';
import {
  approveOrder,
  cancelOrder,
  createOrder,
  fetchLatestOrder,
  fetchOrderPreview,
} from '@/features/order/api';
import { postCycleSkip } from '@/features/cycle/api';
import { pickFirstConnectedStore } from '@/features/order/pickStore';
import {
  MEALPLAN_NOT_FOUND_CODE,
  ORDER_ALREADY_CONFIRMED_CODE,
  ORDER_NOT_FOUND_CODE,
  type OrderBlockedReason,
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
  'ORDER_INVALID_STATE',
  'ORDER_ALREADY_CONFIRMED',
  'ORDER_CANCEL_WINDOW_CLOSED',
  'CYCLE_ALREADY_CONFIRMED',
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

function formatLocalDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale === 'en' ? 'en-US' : 'ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso));
}

function orderChanged(before: OrderResponse, after: OrderResponse): boolean {
  return (
    JSON.stringify(before.items) !== JSON.stringify(after.items) ||
    before.estimatedTotal.amount !== after.estimatedTotal.amount ||
    before.estimatedTotal.currency !== after.estimatedTotal.currency
  );
}

/** `/orders` — latest status 6종을 서버 계약 그대로 분기한다 (ui-design 14-3). */
export function OrdersController() {
  const t = useTranslations('orders');
  const tCommon = useTranslations('common');
  const locale = useLocale();
  const router = useRouter();

  const [status, setStatus] = useState<PageStatus>('loading');
  const [preview, setPreview] = useState<OrderPreviewResponse | null>(null);
  const [connections, setConnections] = useState<StoreConnection[]>([]);
  const [latest, setLatest] = useState<OrderResponse | null>(null);
  const [busyAction, setBusyAction] = useState<
    'create' | 'approve' | 'cancel' | 'skip' | 'refresh' | null
  >(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async (refresh = false) => {
    setStatus('loading');
    setErrorCode(null);
    const [previewRes, storesRes, latestRes] = await Promise.all([
      fetchOrderPreview(refresh),
      fetchStoreConnections(),
      fetchLatestOrder(),
    ]);

    if (
      (!previewRes.ok && previewRes.status === 401) ||
      (!storesRes.ok && storesRes.status === 401) ||
      (!latestRes.ok && latestRes.status === 401)
    ) {
      setStatus('unauthenticated');
      return;
    }

    if (!storesRes.ok) {
      setStatus('error');
      return;
    }

    const nextLatest = latestRes.ok ? latestRes.data : null;
    const latestMissing = !latestRes.ok && latestRes.code === ORDER_NOT_FOUND_CODE;
    if (!latestRes.ok && !latestMissing) {
      setStatus('error');
      return;
    }

    setConnections(storesRes.data.connections);
    setLatest(nextLatest);

    if (previewRes.ok) {
      setPreview(previewRes.data);
      setStatus('ready');
      return;
    }

    setPreview(null);
    if (nextLatest !== null) {
      if (refresh) setErrorCode(previewRes.code);
      setStatus('ready');
      return;
    }
    setStatus(previewRes.code === MEALPLAN_NOT_FOUND_CODE ? 'no-plan' : 'error');
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (status === 'unauthenticated') router.replace('/login?next=/orders');
  }, [status, router]);

  const store: StoreId | null = useMemo(() => {
    if (preview === null) return pickFirstConnectedStore('KR', connections);
    return pickFirstConnectedStore(preview.country, connections);
  }, [preview, connections]);
  const currentLatest = useMemo(
    () =>
      latest !== null && (preview === null || latest.cycleStart === preview.cycleStart)
        ? latest
        : null,
    [latest, preview],
  );

  const errorMessage = (code: string): string => {
    if ((ORDER_ERROR_CODES as readonly string[]).includes(code)) return t(`error.${code}`);
    return tCommon('error.fallback');
  };

  const handleCreate = async () => {
    if (store === null || busyAction !== null || preview === null || preview.needed.length === 0)
      return;
    setBusyAction('create');
    setErrorCode(null);
    const result = await createOrder({ store });
    setBusyAction(null);
    if (result.ok) {
      setLatest(result.data);
      return;
    }
    setErrorCode(result.code);
  };

  const handleApprove = async () => {
    if (latest === null || busyAction !== null) return;
    const before = latest;
    setBusyAction('approve');
    setErrorCode(null);
    setNotice(null);
    const result = await approveOrder(before.id);
    setBusyAction(null);
    if (result.ok) {
      setLatest(result.data);
      if (orderChanged(before, result.data)) setNotice(t('recalculatedNotice'));
      return;
    }
    if (result.code === ORDER_ALREADY_CONFIRMED_CODE) {
      setNotice(t('alreadyConfirmed'));
      const refreshed = await fetchLatestOrder();
      if (refreshed.ok) setLatest(refreshed.data);
      return;
    }
    setErrorCode(result.code);
  };

  const handleCancel = async () => {
    if (latest === null || busyAction !== null) return;
    setBusyAction('cancel');
    setErrorCode(null);
    const result = await cancelOrder(latest.id);
    setBusyAction(null);
    if (result.ok) {
      setLatest(result.data);
      return;
    }
    setErrorCode(result.code);
  };

  const handleSkip = async () => {
    if (busyAction !== null) return;
    setBusyAction('skip');
    setErrorCode(null);
    const result = await postCycleSkip();
    setBusyAction(null);
    if (!result.ok) {
      setErrorCode(result.code);
      return;
    }
    const refreshed = await fetchLatestOrder();
    if (refreshed.ok) setLatest(refreshed.data);
  };

  const handleRefresh = async () => {
    if (busyAction !== null) return;
    setBusyAction('refresh');
    setErrorCode(null);
    await load(true);
    setBusyAction(null);
  };

  if (status === 'loading' || status === 'unauthenticated') {
    return <LoadingPanel label={t('loading')} />;
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
        {status === 'no-plan' ? <NoPlan onHome={() => router.push('/')} /> : null}

        {errorCode ? (
          <ErrorPanel
            message={errorMessage(errorCode)}
            onRetry={() => setErrorCode(null)}
            retryLabel={t('dismiss')}
          />
        ) : null}
        {notice ? (
          <p
            role="status"
            aria-live="polite"
            className="rounded-xl bg-brand-50 p-3 text-xs font-bold text-brand-700"
          >
            {notice}
          </p>
        ) : null}

        {status === 'ready' && currentLatest?.status === 'draft' ? (
          <DraftOrderBody
            order={currentLatest}
            locale={locale}
            busy={busyAction !== null}
            onApprove={() => void handleApprove()}
            onSkip={() => void handleSkip()}
          />
        ) : null}
        {status === 'ready' && currentLatest?.status === 'awaiting_user' ? (
          <DraftOrderBody
            order={currentLatest}
            locale={locale}
            busy={busyAction !== null}
            onApprove={() => void handleApprove()}
            onSkip={() => void handleSkip()}
            onRefresh={() => void handleRefresh()}
            onSettings={() => router.push('/settings')}
          />
        ) : null}
        {status === 'ready' && currentLatest?.status === 'confirmed' ? (
          <ConfirmedSnapshot
            order={currentLatest}
            locale={locale}
            busy={busyAction !== null}
            onCancel={() => void handleCancel()}
          />
        ) : null}
        {status === 'ready' &&
        (currentLatest?.status === 'cancelled' || currentLatest?.status === 'expired') ? (
          <TerminalOrderState order={currentLatest} locale={locale} />
        ) : null}
        {status === 'ready' && currentLatest?.status === 'failed' ? (
          <FailedOrderState busy={busyAction !== null} onRefresh={() => void handleRefresh()} />
        ) : null}
        {status === 'ready' && currentLatest === null && preview !== null ? (
          <ReviewBody
            preview={preview}
            locale={locale}
            store={store}
            confirming={busyAction === 'create'}
            errorCode={errorCode}
            onConfirm={() => void handleCreate()}
            onSettings={() => router.push('/settings')}
          />
        ) : null}
      </main>
    </div>
  );
}

function LoadingPanel({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={label}
      className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col gap-3.5 bg-surface-app px-[18px] pb-6 pt-8 sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card"
    >
      <div aria-hidden className="h-[48px] animate-pulse rounded-[14px] bg-white shadow-card" />
      <div aria-hidden className="h-[180px] animate-pulse rounded-[20px] bg-white shadow-card" />
      <div aria-hidden className="h-[120px] animate-pulse rounded-[20px] bg-white shadow-card" />
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

function NoPlan({ onHome }: { onHome: () => void }) {
  const t = useTranslations('orders');
  return (
    <section className="rounded-[20px] bg-white p-5 shadow-card">
      <h2 className="text-[15px] font-extrabold text-navy-900">{t('emptyMealplan.title')}</h2>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-500">
        {t('emptyMealplan.description')}
      </p>
      <button
        type="button"
        onClick={onHome}
        className="mt-4 w-full rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta"
      >
        {t('emptyMealplan.cta')}
      </button>
    </section>
  );
}

function DraftOrderBody({
  order,
  locale,
  busy,
  onApprove,
  onSkip,
  onRefresh,
  onSettings,
}: {
  order: OrderResponse;
  locale: string;
  busy: boolean;
  onApprove: () => void;
  onSkip: () => void;
  onRefresh?: () => void;
  onSettings?: () => void;
}) {
  const t = useTranslations('orders');
  const needed = order.items.filter((item) => item.lineType === 'needed');
  const covered = order.items.filter((item) => item.lineType === 'covered');
  return (
    <>
      <StatusHeader status={order.status} />
      {order.status === 'awaiting_user' && order.blockedReason ? (
        <BlockedOrderBanner
          reason={order.blockedReason}
          busy={busy}
          onApprove={onApprove}
          onRefresh={onRefresh ?? onApprove}
          onSettings={onSettings ?? onApprove}
        />
      ) : null}
      <SnapshotList title={t('needed.title')} items={needed} locale={locale} />
      {covered.length > 0 ? (
        <SnapshotList title={t('covered.title')} items={covered} locale={locale} />
      ) : null}
      <section className="rounded-[20px] bg-white p-4 shadow-card">
        <Total money={order.estimatedTotal} locale={locale} />
        <p className="mt-3 text-[12.5px] font-semibold leading-relaxed text-ink-600">
          {t('simulationNotice')}
        </p>
        {order.autoConfirmAt ? (
          <p className="mt-2 text-xs font-bold text-brand-700">
            {t('autoConfirmAt', {
              time: formatLocalDateTime(order.autoConfirmAt, locale),
            })}
          </p>
        ) : null}
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onApprove}
            className="rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta disabled:opacity-40"
          >
            {busy ? t('approving') : t('approveCta')}
          </button>
          <button
            type="button"
            disabled
            aria-disabled="true"
            className="rounded-[14px] bg-[#F0F2F6] px-4 py-3 text-sm font-bold text-ink-400 opacity-60"
          >
            {t('editItemsCta')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onSkip}
            className="col-span-2 rounded-[14px] bg-[#F0F2F6] px-4 py-3 text-sm font-bold text-ink-600 disabled:opacity-40"
          >
            {t('skipCta')}
          </button>
        </div>
      </section>
    </>
  );
}

function BlockedOrderBanner({
  reason,
  busy,
  onApprove,
  onRefresh,
  onSettings,
}: {
  reason: OrderBlockedReason;
  busy: boolean;
  onApprove: () => void;
  onRefresh: () => void;
  onSettings: () => void;
}) {
  const t = useTranslations('cycle');
  const action =
    reason === 'STORE_DISCONNECTED'
      ? onSettings
      : reason === 'AUTO_CONFIRM_OFF' || reason === 'BUDGET_EXCEEDED'
        ? onApprove
        : onRefresh;
  return (
    <div role="alert" className="rounded-[16px] border border-flame-200 bg-white p-4 shadow-card">
      <p className="text-sm font-extrabold text-navy-900">{t(`blocked.${reason}.title`)}</p>
      <button
        type="button"
        disabled={busy}
        onClick={action}
        className="mt-3 rounded-xl bg-navy-900 px-4 py-2.5 text-xs font-extrabold text-white disabled:opacity-50"
      >
        {t(`blocked.${reason}.cta`)}
      </button>
    </div>
  );
}

function ReviewBody({
  preview,
  locale,
  store,
  confirming,
  errorCode,
  onConfirm,
  onSettings,
}: {
  preview: OrderPreviewResponse;
  locale: string;
  store: StoreId | null;
  confirming: boolean;
  errorCode: string | null;
  onConfirm: () => void;
  onSettings: () => void;
}) {
  const t = useTranslations('orders');
  const neededEmpty = preview.needed.length === 0;
  const showNoStore = store === null || errorCode === 'STORE_NOT_CONNECTED';
  return (
    <>
      {showNoStore ? <NoStore onSettings={onSettings} /> : null}
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
        <Total money={preview.estimatedTotal} locale={locale} />
        {preview.country === 'KR' ? (
          <p className="mt-1.5 text-[11.5px] text-ink-400">{t('estimateSource')}</p>
        ) : null}
        <p className="mt-3 text-[12.5px] font-semibold leading-relaxed text-ink-600">
          {t('simulationNotice')}
        </p>
        <button
          type="button"
          disabled={neededEmpty || store === null || confirming}
          onClick={onConfirm}
          className="mt-3 w-full rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta disabled:opacity-40"
        >
          {confirming ? t('confirming') : t('confirmCta')}
        </button>
      </section>
    </>
  );
}

function NoStore({ onSettings }: { onSettings: () => void }) {
  const t = useTranslations('orders');
  return (
    <div role="alert" className="rounded-[16px] border border-flame-200 bg-white p-4 shadow-card">
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
  );
}

function StatusHeader({ status }: { status: OrderResponse['status'] }) {
  const t = useTranslations('orders');
  const key = status === 'awaiting_user' ? 'awaitingUser' : status;
  return (
    <section className="rounded-[20px] bg-white p-4 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[14.5px] font-extrabold text-navy-900">{t('title')}</h2>
        <Badge tone={status === 'confirmed' ? 'brand' : 'neutral'}>{t(`status.${key}`)}</Badge>
      </div>
    </section>
  );
}

function ConfirmedSnapshot({
  order,
  locale,
  busy,
  onCancel,
}: {
  order: OrderResponse;
  locale: string;
  busy: boolean;
  onCancel: () => void;
}) {
  const t = useTranslations('orders');
  const needed = order.items.filter((item) => item.lineType === 'needed');
  const covered = order.items.filter((item) => item.lineType === 'covered');
  return (
    <>
      <StatusHeader status={order.status} />
      <section className="rounded-[20px] bg-white p-4 shadow-card">
        {order.autoConfirmed ? <Badge tone="brand">{t('autoConfirmedBadge')}</Badge> : null}
        <p className="mt-2 text-[12.5px] font-semibold leading-relaxed text-ink-600">
          {t('simulationNotice')}
        </p>
        {order.deliveryEta ? (
          <p role="status" aria-live="polite" className="mt-2 text-[13px] font-bold text-mint-700">
            {t('deliveryEta', { date: formatLocalDateTime(order.deliveryEta, locale) })}
          </p>
        ) : null}
        <SnapshotList title={t('needed.title')} items={needed} locale={locale} />
        {covered.length > 0 ? (
          <SnapshotList title={t('covered.title')} items={covered} locale={locale} />
        ) : null}
        <div className="mt-3 border-t border-ink-50 pt-3">
          <Total money={order.estimatedTotal} locale={locale} />
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={onCancel}
          className="mt-3 w-full rounded-[14px] bg-[#F0F2F6] px-4 py-3 text-sm font-extrabold text-ink-600 disabled:opacity-40"
        >
          {t('cancelCta')}
        </button>
      </section>
    </>
  );
}

function TerminalOrderState({ order, locale }: { order: OrderResponse; locale: string }) {
  const t = useTranslations('orders');
  const key = order.status === 'cancelled' ? 'cancelled' : 'expired';
  return (
    <section className="rounded-[20px] bg-white p-5 shadow-card">
      <Badge tone="neutral">{t(`status.${key}`)}</Badge>
      <h2 className="mt-3 text-[15px] font-extrabold text-navy-900">
        {t(`terminal.${key}.title`)}
      </h2>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-500">
        {t(`terminal.${key}.body`, {
          date: formatLocalDateTime(order.nextSuggestedAt, locale),
        })}
      </p>
    </section>
  );
}

function FailedOrderState({ busy, onRefresh }: { busy: boolean; onRefresh: () => void }) {
  const t = useTranslations('orders');
  return (
    <section className="rounded-[20px] bg-white p-5 shadow-card">
      <Badge tone="neutral">{t('status.failed')}</Badge>
      <h2 className="mt-3 text-[15px] font-extrabold text-navy-900">
        {t('terminal.failed.title')}
      </h2>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-500">
        {t('terminal.failed.body')}
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={onRefresh}
        className="mt-4 w-full rounded-[14px] bg-brand-600 px-4 py-3 text-sm font-extrabold text-white shadow-cta disabled:opacity-40"
      >
        {busy ? t('recalculating') : t('recalculateCta')}
      </button>
    </section>
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
                        <MoneyText
                          money={matched.price}
                          locale={locale}
                          className="shrink-0 font-bold"
                        />
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
    <section className="rounded-[20px] bg-white p-4 shadow-card">
      <h3 className="mb-1.5 text-xs font-bold text-ink-400">{title}</h3>
      <ul className="flex flex-col divide-y divide-ink-50">
        {items.map((item) => (
          <li
            key={`${item.lineType}-${item.name}-${item.unit}`}
            className="flex flex-col gap-0.5 py-2"
          >
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
                    <MoneyText
                      money={item.unitPrice}
                      locale={locale}
                      className="shrink-0 font-bold"
                    />
                  ) : null}
                </span>
              ) : (
                <span className="text-[12px] text-ink-300">{t('noPrice')}</span>
              )
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Total({ money, locale }: { money: OrderResponse['estimatedTotal']; locale: string }) {
  const t = useTranslations('orders');
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[13px] font-bold text-ink-500">{t('estimateTotal')}</span>
      <MoneyText
        money={money}
        locale={locale}
        className="text-[16px] font-extrabold text-navy-900"
      />
    </div>
  );
}
