'use client';

import { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from '@/i18n/routing';
import { formatMoney } from '@/shared/ui/MoneyText';
import { GenerationLoading } from '@/features/mealplan/GenerationLoading';
import { AccountCard } from '@/features/settings/AccountCard';
import { RegionCard } from '@/features/settings/RegionCard';
import { DietSettingsCard } from '@/features/settings/DietSettingsCard';
import { StoreConnectionsCard } from '@/features/settings/StoreConnectionsCard';
import { EditOverlay, type SettingsEditResult } from '@/features/settings/EditOverlay';
import { ConfirmSheet } from '@/features/settings/ConfirmSheet';
import { useSettings, type DietSection } from '@/features/settings/useSettings';
import type { StoreId } from '@/features/store/types';
import type { Country, Money } from '@/shared/api/types';

/** 상단 배너 오류 종류 → settings.error.{key} */
type PageError = 'store' | 'generate' | 'rateLimited' | 'logout' | 'region' | null;

/**
 * 설정 페이지 컨트롤러 (ui-design 9장, FR-401~404)
 * 계정 카드 → 내 식생활 설정 3행(단일 편집 → 재생성 확인) → 스토어 연동 리스트.
 */
export function SettingsController() {
  const t = useTranslations('settings');
  const tDirection = useTranslations('budgetDraft.direction');
  const tCuisine = useTranslations('cuisine');
  const tStore = useTranslations('store');
  const locale = useLocale();
  const router = useRouter();
  const settings = useSettings();

  const [editSection, setEditSection] = useState<DietSection | null>(null);
  const [editError, setEditError] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [storeConfirm, setStoreConfirm] = useState<{ store: StoreId; connect: boolean } | null>(
    null,
  );
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [regionConfirm, setRegionConfirm] = useState<Country | null>(null);
  const [pageError, setPageError] = useState<PageError>(null);

  // 미인증(쿠키 무효 401) — 미들웨어 통과 후 세션 만료 케이스 → 로그인으로 (ui-design 1장 규칙)
  useEffect(() => {
    if (settings.status === 'unauthenticated') {
      router.replace('/login?next=/settings');
    }
  }, [settings.status, router]);

  const currency: Money['currency'] = settings.user?.currency === 'USD' ? 'USD' : 'KRW';

  const openEdit = useCallback((section: DietSection) => {
    setEditError(false);
    setEditSection(section);
  }, []);

  // FR-402/403: 단일 편집 저장 → 성공 시 재생성 확인 시트
  const handleEditSave = useCallback(
    async (result: SettingsEditResult) => {
      setEditError(false);
      const ok =
        result.section === 'household'
          ? await settings.saveHousehold(result.members)
          : result.section === 'budget'
            ? await settings.saveBudget(result.amount, result.locked)
            : await settings.savePreference(result.cuisines, result.direction);
      if (!ok) {
        setEditError(true);
        return;
      }
      setEditSection(null);
      setRegenerateOpen(true);
    },
    [settings],
  );

  // FR-403: 수락 → 재생성(로딩 재사용) 후 홈 / 거절 → 설정 잔류
  const handleRegenerate = useCallback(async () => {
    setRegenerateOpen(false);
    const outcome = await settings.regenerate();
    if (outcome === 'ok') {
      router.replace('/');
      return;
    }
    setPageError(outcome === 'rate-limited' ? 'rateLimited' : 'generate');
  }, [settings, router]);

  // FR-404: 연동/해제 확인 시트 → PUT
  const handleStoreConfirm = useCallback(async () => {
    if (storeConfirm === null) return;
    const { store, connect } = storeConfirm;
    setStoreConfirm(null);
    const ok = await settings.toggleStore(store, connect);
    if (!ok) setPageError('store');
  }, [storeConfirm, settings]);

  // FR-601: 지역 전환 확인 → PUT /users/me/region (통화·스토어 세트 갱신)
  const handleRegionConfirm = useCallback(async () => {
    if (regionConfirm === null) return;
    const target = regionConfirm;
    setRegionConfirm(null);
    const ok = await settings.switchRegion(target);
    if (!ok) setPageError('region');
  }, [regionConfirm, settings]);

  // FR-401: 로그아웃 → visited 마커(훅) → 게스트 홈
  const handleLogout = useCallback(async () => {
    const ok = await settings.logout();
    setLogoutOpen(false);
    if (!ok) {
      setPageError('logout');
      return;
    }
    router.replace('/');
    router.refresh();
  }, [settings, router]);

  if (settings.status === 'loading' || settings.status === 'unauthenticated') {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label={t('loading')}
        className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col gap-3.5 bg-surface-app px-[18px] pb-6 pt-8 sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card"
      >
        <div aria-hidden className="h-[80px] animate-pulse rounded-[18px] bg-white shadow-card" />
        <div aria-hidden className="h-[170px] animate-pulse rounded-[18px] bg-white shadow-card" />
        <div aria-hidden className="h-[230px] animate-pulse rounded-[18px] bg-white shadow-card" />
      </div>
    );
  }

  if (settings.status === 'error' || settings.user === null || settings.connections === null) {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col items-center justify-center gap-4 bg-surface-app px-[18px] sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card">
        <p role="alert" className="text-center text-sm font-semibold text-ink-600">
          {t('error.load')}
        </p>
        <button
          type="button"
          onClick={settings.reload}
          className="rounded-2xl bg-brand-600 px-6 py-3 text-sm font-extrabold text-white shadow-cta"
        >
          {t('error.reload')}
        </button>
      </div>
    );
  }

  const { user, members, budget, profile, connections } = settings;

  const householdSummary =
    members !== null ? t('diet.householdSummary', { count: members.length }) : t('diet.notSet');
  const preferenceSummary = profile.known
    ? [tDirection(profile.direction), ...profile.cuisines.map((cuisine) => tCuisine(cuisine))].join(
        ' · ',
      )
    : t('diet.configured');
  const budgetSummary =
    budget !== null
      ? t('diet.budgetSummary', { amount: formatMoney(budget, locale) })
      : user.hasBudgetPlan
        ? t('diet.configured')
        : t('diet.notSet');

  const pageErrorBanner =
    pageError !== null ? (
      <div
        role="alert"
        className="mb-3.5 flex items-start justify-between gap-3 rounded-2xl border border-flame-200 bg-white p-4 shadow-card"
      >
        <p className="text-[13px] font-semibold text-ink-600">{t(`error.${pageError}`)}</p>
        <button
          type="button"
          onClick={() => setPageError(null)}
          className="shrink-0 rounded-[10px] bg-[#F0F2F6] px-3 py-1.5 text-xs font-bold text-ink-500"
        >
          {t('error.dismiss')}
        </button>
      </div>
    ) : null;

  return (
    <>
      <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col bg-surface-app sm:min-h-0 sm:my-6 sm:overflow-hidden sm:rounded-[32px] sm:shadow-card">
        {/* 헤더 — 뒤로가기(홈) + 타이틀 (프로토타입 settings 헤더) */}
        <header className="flex items-center gap-3 border-b border-[#EEF1F6] bg-white px-[18px] pb-3.5 pt-8">
          <button
            type="button"
            aria-label={t('backLabel')}
            onClick={() => router.push('/')}
            className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[10px] bg-surface-app"
          >
            <svg aria-hidden width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M15 5l-7 7 7 7"
                stroke="#16223B"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <h1 className="text-[19px] font-extrabold tracking-tight text-navy-900">{t('title')}</h1>
        </header>

        <main className="flex-1 px-[18px] pb-8 pt-[18px]">
          {pageErrorBanner}
          <AccountCard
            nickname={user.nickname}
            email={user.email}
            onLogout={() => setLogoutOpen(true)}
          />
          <RegionCard
            country={user.country}
            busy={settings.switchingRegion}
            onSwitch={(target) => setRegionConfirm(target)}
          />
          <DietSettingsCard
            householdSummary={householdSummary}
            preferenceSummary={preferenceSummary}
            budgetSummary={budgetSummary}
            onEdit={openEdit}
          />
          <StoreConnectionsCard
            connections={connections}
            storeIds={settings.storeIds}
            email={user.email}
            busyStore={settings.togglingStore}
            onToggle={(store, next) => setStoreConfirm({ store, connect: next })}
          />
        </main>
      </div>

      {/* 단일 편집 오버레이 (FR-402) */}
      {editSection !== null ? (
        <EditOverlay
          section={editSection}
          currency={currency}
          initialMembers={members}
          initialBudget={budget}
          initialLocked={profile.locked}
          initialCuisines={profile.cuisines}
          initialDirection={profile.direction}
          saving={settings.saving}
          saveError={editError}
          onCancel={() => setEditSection(null)}
          onSave={(result) => void handleEditSave(result)}
        />
      ) : null}

      {/* 저장 성공 → 재생성 확인 (FR-403) */}
      <ConfirmSheet
        open={regenerateOpen}
        title={t('regenerate.title')}
        description={t('regenerate.description')}
        confirmLabel={t('regenerate.confirm')}
        cancelLabel={t('regenerate.decline')}
        onConfirm={() => void handleRegenerate()}
        onCancel={() => setRegenerateOpen(false)}
      />

      {/* 스토어 연동/해제 확인 (FR-404 — 1단계: 연동 표시만 안내) */}
      <ConfirmSheet
        open={storeConfirm !== null}
        title={
          storeConfirm !== null
            ? t(storeConfirm.connect ? 'stores.connectConfirm.title' : 'stores.disconnectConfirm.title', {
                store: tStore(`${storeConfirm.store}.name`),
              })
            : ''
        }
        description={t(
          storeConfirm?.connect === false
            ? 'stores.disconnectConfirm.description'
            : 'stores.connectConfirm.description',
        )}
        confirmLabel={t(
          storeConfirm?.connect === false
            ? 'stores.disconnectConfirm.confirm'
            : 'stores.connectConfirm.confirm',
        )}
        cancelLabel={t('stores.confirmCancel')}
        destructive={storeConfirm?.connect === false}
        busy={settings.togglingStore !== null}
        onConfirm={() => void handleStoreConfirm()}
        onCancel={() => setStoreConfirm(null)}
      />

      {/* 지역 전환 확인 (FR-601/606 — 기존 플랜 통화 유지 안내) */}
      <ConfirmSheet
        open={regionConfirm !== null}
        title={t('region.switchConfirm.title')}
        description={t('region.switchConfirm.description')}
        confirmLabel={t('region.switchConfirm.confirm')}
        cancelLabel={t('region.switchConfirm.cancel')}
        busy={settings.switchingRegion}
        onConfirm={() => void handleRegionConfirm()}
        onCancel={() => setRegionConfirm(null)}
      />

      {/* 로그아웃 확인 (FR-401) */}
      <ConfirmSheet
        open={logoutOpen}
        title={t('account.logoutConfirm.title')}
        description={t('account.logoutConfirm.description')}
        confirmLabel={t('account.logoutConfirm.confirm')}
        cancelLabel={t('account.logoutConfirm.cancel')}
        destructive
        busy={settings.loggingOut}
        onConfirm={() => void handleLogout()}
        onCancel={() => setLogoutOpen(false)}
      />

      {/* 재생성 로딩 재사용 (FR-403) */}
      {settings.generating ? <GenerationLoading /> : null}
    </>
  );
}
