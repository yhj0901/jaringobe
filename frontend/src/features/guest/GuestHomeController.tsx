'use client';

import { useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { HomeShell } from '@/features/home/HomeShell';
import { useGuestStore } from '@/features/guest/store';
import {
  getDefaultViewModel,
  getSampleViewModel,
  toBudgetBand,
  toHouseholdBand,
} from '@/features/guest/sampleMatrix';
import { useEngagementTiming } from '@/features/guest/useEngagementTiming';
import { EngagementPrompt } from '@/features/guest/EngagementPrompt';
import { OnboardingWizard } from '@/features/household/OnboardingWizard';
import { PersistentCtaBanner } from '@/features/guest/PersistentCtaBanner';
import { AutoOrderPrompt } from '@/features/guest/AutoOrderPrompt';
import { RevisitPrompt } from '@/features/guest/RevisitPrompt';
import { SignupGateModal } from '@/features/auth/SignupGateModal';
import { RecipeSheet } from '@/features/mealplan/RecipeSheet';
import {
  PROMPT_DECLINED_SESSION_KEY,
  REVISIT_SHOWN_SESSION_KEY,
  VISITED_MARKER_KEY,
} from '@/shared/config/constants';
import { useRouter, type AppLocale } from '@/i18n/routing';
import type { OnboardingResult } from '@/features/household/types';
import type { MealItem } from '@/features/home/types';

/** 예산안 적용 연출 시간 (FR-105 — 300ms 미만) */
const APPLY_TRANSITION_MS = 250;

/**
 * 게스트 홈 컨트롤러 (ui-design 2장)
 * localStorage 복원 → HomeViewModel 생성/갱신, 타이밍 프롬프트·예산안 플로우·자동주문 전환 담당.
 */
export function GuestHomeController() {
  const locale = useLocale() as AppLocale;
  const t = useTranslations('guestHome');
  const router = useRouter();

  const plan = useGuestStore((state) => state.plan);
  const autoOrderNotifiedAt = useGuestStore((state) => state.promptHistory.autoOrderNotifiedAt);
  const setPlan = useGuestStore((state) => state.setPlan);
  const markAutoOrderNotified = useGuestStore((state) => state.markAutoOrderNotified);

  const [hydrated, setHydrated] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [draftOpen, setDraftOpen] = useState(false);
  const [applying, setApplying] = useState(false);
  const [autoOrderPromptOpen, setAutoOrderPromptOpen] = useState(false);
  const [gateOpen, setGateOpen] = useState(false);
  const [revisitOpen, setRevisitOpen] = useState(false);
  const [recipeMeal, setRecipeMeal] = useState<MealItem | null>(null);

  // FR-107: 마운트 후 localStorage 복원 (30일 만료는 스토리지 래퍼가 검사)
  useEffect(() => {
    void useGuestStore.persist.rehydrate();
    setHydrated(true);
    if (window.sessionStorage.getItem(PROMPT_DECLINED_SESSION_KEY) !== null) {
      setDeclined(true);
    }
    // FR-316: 로그인 이력 재방문자 → [로그인하기/구경하기] 알림 (세션 내 1회)
    if (
      window.localStorage.getItem(VISITED_MARKER_KEY) !== null &&
      window.sessionStorage.getItem(REVISIT_SHOWN_SESSION_KEY) === null
    ) {
      window.sessionStorage.setItem(REVISIT_SHOWN_SESSION_KEY, '1');
      setRevisitOpen(true);
    }
  }, []);

  // FR-106: guest-planned 진입 시 자동주문 알림 1회 (promptHistory 기록)
  useEffect(() => {
    if (hydrated && plan && autoOrderNotifiedAt === undefined && !applying) {
      setAutoOrderPromptOpen(true);
      markAutoOrderNotified();
    }
  }, [hydrated, plan, autoOrderNotifiedAt, applying, markAutoOrderNotified]);

  const viewModel = useMemo(() => {
    if (!hydrated || !plan) return getDefaultViewModel(locale);
    return getSampleViewModel(
      locale,
      {
        householdBand: toHouseholdBand(plan.householdSize),
        budgetBand: toBudgetBand(plan.amount, locale),
        direction: plan.mealDirection,
      },
      'guest-planned',
    );
  }, [hydrated, plan, locale]);

  // FR-102: 예산안 미작성 게스트에게만 타이밍 프롬프트 (재방문 알림 중에는 보류)
  useEngagementTiming({
    enabled: hydrated && !plan && !draftOpen && !revisitOpen,
    onTrigger: () => setPromptOpen(true),
  });

  const goLogin = () => {
    router.push('/login?next=/');
  };

  // 진입 철학: 예산 짜보기가 항상 로그인보다 먼저 (로그인은 자동주문 시점에만)
  // 예산안 미작성 게스트의 잠긴 기능 클릭 → 가입 게이트 대신 예산안 작성 유도
  const gateOrDraft = () => {
    if (!plan) {
      setPromptOpen(false);
      setDraftOpen(true);
    } else {
      setGateOpen(true);
    }
  };

  const handleDecline = () => {
    // FR-103: 세션 내 재노출 금지 + 상시 CTA 배너 대체
    window.sessionStorage.setItem(PROMPT_DECLINED_SESSION_KEY, '1');
    setPromptOpen(false);
    setDeclined(true);
  };

  const handleAccept = () => {
    setPromptOpen(false);
    setDraftOpen(true);
  };

  const handleComplete = (result: OnboardingResult) => {
    // FR-105: 적용 연출(로딩 트랜지션) 후 홈 전체 갱신
    // OnboardingResult 는 GuestPlan(옵셔널 확장 포함)과 필드 호환 — 그대로 저장
    setDraftOpen(false);
    setApplying(true);
    setPlan(result);
    window.setTimeout(() => setApplying(false), APPLY_TRANSITION_MS);
  };

  const showCtaBanner = hydrated && declined && !plan && !draftOpen;

  return (
    <>
      {showCtaBanner ? <PersistentCtaBanner onClick={() => setDraftOpen(true)} /> : null}
      {applying ? (
        <div
          role="status"
          className="fixed inset-0 z-50 flex items-center justify-center bg-surface/85 text-sm font-bold text-navy-900 backdrop-blur-sm"
        >
          {t('applying')}
        </div>
      ) : null}
      <HomeShell
        viewModel={viewModel}
        onAutoOrderStart={goLogin}
        onRecipeClick={(meal) => setRecipeMeal(meal)}
        onLockedNavClick={gateOrDraft}
        onAvatarClick={() => setGateOpen(true)}
      />
      <RecipeSheet
        meal={recipeMeal}
        householdSize={plan?.householdSize}
        onClose={() => setRecipeMeal(null)}
      />
      <RevisitPrompt
        open={revisitOpen}
        onLogin={goLogin}
        onBrowse={() => setRevisitOpen(false)}
      />
      <EngagementPrompt open={promptOpen} onAccept={handleAccept} onDecline={handleDecline} />
      {/* 게스트 체험도 가입 온보딩과 동일한 3스텝 위저드 사용 (BudgetDraftFlow 대체) */}
      {draftOpen ? (
        <OnboardingWizard
          mode="guest"
          onComplete={handleComplete}
          onClose={() => setDraftOpen(false)}
        />
      ) : null}
      <AutoOrderPrompt
        open={autoOrderPromptOpen}
        onStart={goLogin}
        onLater={() => setAutoOrderPromptOpen(false)}
      />
      <SignupGateModal open={gateOpen} onLogin={goLogin} onClose={() => setGateOpen(false)} />
    </>
  );
}
