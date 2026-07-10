'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { HomeShell } from '@/features/home/HomeShell';
import { MEAL_SECTION_ID } from '@/features/home/MealPlanSection';
import { GuestHomeController } from '@/features/guest/GuestHomeController';
import { getDefaultViewModel } from '@/features/guest/sampleMatrix';
import { useMemberHome, type PlanCreateInput } from '@/features/mealplan/useMemberHome';
import { PlanCreateSheet } from '@/features/mealplan/PlanCreateSheet';
import { GenerationLoading } from '@/features/mealplan/GenerationLoading';
import { OverBudgetBanner } from '@/features/mealplan/OverBudgetBanner';
import { OnboardingCtaBanner } from '@/features/mealplan/OnboardingCtaBanner';
import { RegenerateConfirmSheet } from '@/features/mealplan/RegenerateConfirmSheet';
import { RecipeSheet } from '@/features/mealplan/RecipeSheet';
import { LOCKED_NOTICE_MS } from '@/features/mealplan/constants';
import { useRouter, type AppLocale } from '@/i18n/routing';
import type { MealItem } from '@/features/home/types';

/**
 * 회원 홈 컨트롤러 (ui-design 7장·8장) — useMemberHome 분기별 화면 구성.
 * 게스트 홈(GuestHomeController)과 동일한 홈 셸을 회원 실데이터로 채운다 (FR-201).
 * 식단 없음/예산 없음은 빈 히어로 전면 대신 샘플 홈 + 상단 배너 (FR-316).
 */
export function MemberHomeController() {
  const t = useTranslations('memberHome');
  const locale = useLocale() as AppLocale;
  const router = useRouter();
  const home = useMemberHome();

  const [createOpen, setCreateOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [lockedNotice, setLockedNotice] = useState(false);
  const [recipeMeal, setRecipeMeal] = useState<MealItem | null>(null);
  const noticeTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (noticeTimerRef.current !== null) window.clearTimeout(noticeTimerRef.current);
    },
    [],
  );

  const showLockedNotice = useCallback(() => {
    setLockedNotice(true);
    if (noticeTimerRef.current !== null) window.clearTimeout(noticeTimerRef.current);
    noticeTimerRef.current = window.setTimeout(() => setLockedNotice(false), LOCKED_NOTICE_MS);
  }, []);

  const handleCreateSubmit = (input: PlanCreateInput) => {
    setCreateOpen(false);
    void home.createPlan(input);
  };

  // ui-design 9장: 회원 홈 헤더 GB 아바타 → 설정 페이지 (FR-401)
  const goSettings = () => {
    router.push('/settings');
  };

  const handleLockedNav = (tab: 'meal' | 'fridge' | 'cart') => {
    // FR-208: meal 탭은 식단 섹션 스크롤, fridge/cart 는 "준비 중" 안내 (가입 게이트 아님)
    if (tab === 'meal') {
      document.getElementById(MEAL_SECTION_ID)?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    showLockedNotice();
  };

  if (home.status === 'loading') {
    return (
      <div
        role="status"
        aria-busy="true"
        aria-label={t('loading.home')}
        className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col gap-3.5 bg-surface-app px-[18px] pb-6 pt-8 sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card"
      >
        <div aria-hidden className="h-[150px] animate-pulse rounded-3xl bg-navy-900/10" />
        <div aria-hidden className="h-[180px] animate-pulse rounded-[20px] bg-white shadow-card" />
        <div aria-hidden className="h-[110px] animate-pulse rounded-[20px] bg-white shadow-card" />
      </div>
    );
  }

  if (home.status === 'guest') {
    // 쿠키는 있었지만 세션 무효(401) — 게스트 홈으로 폴백 (게스트 동작 불변)
    return <GuestHomeController />;
  }

  if (home.status === 'error') {
    return (
      <div className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col items-center justify-center gap-4 bg-surface-app px-[18px] sm:min-h-0 sm:my-6 sm:rounded-[32px] sm:shadow-card">
        <p role="alert" className="text-center text-sm font-semibold text-ink-600">
          {t('error.loadFailed')}
        </p>
        <button
          type="button"
          onClick={home.reload}
          className="rounded-2xl bg-brand-600 px-6 py-3 text-sm font-extrabold text-white shadow-cta"
        >
          {t('error.reload')}
        </button>
      </div>
    );
  }

  const generating = home.generation !== 'idle';

  // FR-204: 실패 → 재시도 배너 / 429 → 대기 안내
  const generationErrorBanner =
    home.generationError !== null ? (
      <div
        role={home.generationError === 'failed' ? 'alert' : 'status'}
        className="mb-3.5 flex flex-col gap-2 rounded-[16px] border border-flame-200 bg-white p-4 shadow-card"
      >
        <p className="text-[13px] font-semibold text-ink-600">
          {home.generationError === 'rate-limited'
            ? t('error.rateLimited')
            : t('error.generateFailed')}
        </p>
        <div className="flex gap-2">
          {home.generationError === 'failed' ? (
            <button
              type="button"
              disabled={generating}
              onClick={() => void home.retryGenerate()}
              className="rounded-[12px] bg-brand-600 px-4 py-2 text-xs font-extrabold text-white disabled:opacity-60"
            >
              {t('error.retry')}
            </button>
          ) : null}
          <button
            type="button"
            onClick={home.dismissGenerationError}
            className="rounded-[12px] bg-[#F0F2F6] px-4 py-2 text-xs font-bold text-ink-500"
          >
            {t('error.dismiss')}
          </button>
        </div>
      </div>
    ) : null;

  const lockedNoticeToast = lockedNotice ? (
    <p
      role="status"
      className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 whitespace-nowrap rounded-full bg-navy-800 px-4 py-2 text-xs font-bold text-white shadow-card"
    >
      {t('locked.notice')}
    </p>
  ) : null;

  if (home.status === 'empty' || home.status === 'budget-required') {
    // FR-316: 빈 히어로/예산 게이트 전면 노출 제거 — 샘플 홈(체험 배지 없음) + 상단 고정 배너
    const needsOnboarding =
      home.status === 'budget-required' || home.onboardingCompleted === false;
    return (
      <>
        <HomeShell
          viewModel={getDefaultViewModel(locale)}
          hideTrialBadge
          topSlot={
            <>
              {generationErrorBanner}
              <OnboardingCtaBanner
                variant={needsOnboarding ? 'setup' : 'create'}
                busy={generating}
                onClick={() => {
                  if (needsOnboarding) {
                    router.push('/onboarding');
                  } else {
                    setCreateOpen(true);
                  }
                }}
              />
            </>
          }
          onRecipeClick={showLockedNotice}
          onLockedNavClick={handleLockedNav}
          onAvatarClick={goSettings}
        />
        {needsOnboarding ? null : (
          <PlanCreateSheet
            open={createOpen}
            busy={generating}
            onClose={() => setCreateOpen(false)}
            onSubmit={handleCreateSubmit}
          />
        )}
        {generating ? <GenerationLoading /> : null}
        {lockedNoticeToast}
      </>
    );
  }

  // status === 'ready'
  const viewModel = home.viewModel;
  if (viewModel === null) return null;

  return (
    <>
      <HomeShell
        viewModel={viewModel}
        topSlot={
          <>
            {viewModel.overBudget === true ? (
              <OverBudgetBanner busy={generating} onRegenerate={() => setConfirmOpen(true)} />
            ) : null}
            {generationErrorBanner}
          </>
        }
        onSelectDate={home.selectDate}
        onRegenerateClick={() => setConfirmOpen(true)}
        onRecipeClick={(meal) => setRecipeMeal(meal)}
        onToggleMealComplete={(meal) => {
          if (meal.mealId !== undefined) void home.toggleMealCompletion(meal.mealId);
        }}
        pendingMealIds={home.pendingMealIds}
        onLockedNavClick={handleLockedNav}
        onAvatarClick={goSettings}
      />
      <RegenerateConfirmSheet
        open={confirmOpen}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => {
          setConfirmOpen(false);
          void home.regeneratePlan();
        }}
      />
      <RecipeSheet
        meal={recipeMeal}
        householdSize={home.householdSize ?? undefined}
        onClose={() => setRecipeMeal(null)}
      />
      {generating ? <GenerationLoading /> : null}
      {lockedNoticeToast}
    </>
  );
}
