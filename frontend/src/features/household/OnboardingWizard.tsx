'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from '@/i18n/routing';
import { GenerationLoading } from '@/features/mealplan/GenerationLoading';
import {
  MEALPLAN_DAYS_DEFAULT,
  MEALPLAN_MEALS_PER_DAY,
} from '@/features/mealplan/constants';
import { createMealPlan } from '@/features/mealplan/api';
import { putBudgetPlan, putHouseholdMembers } from '@/features/household/api';
import {
  budgetRange,
  buildPresetMembers,
  canAddMember,
  canChangeAge,
  canRemoveMember,
  clampBudget,
  type WizardMember,
} from '@/features/household/onboardingLogic';
import { MEMBER_TYPES, type PresetSize } from '@/features/household/constants';
import {
  clearOnboardingPrefill,
  readOnboardingPrefill,
} from '@/features/household/prefill';
import { MemberStep } from '@/features/household/MemberStep';
import { BudgetStep } from '@/features/household/BudgetStep';
import { PreferenceStep } from '@/features/household/PreferenceStep';
import type {
  Cuisine,
  HouseholdMemberType,
  OnboardingResult,
} from '@/features/household/types';
import type { MealDirection, Money } from '@/shared/api/types';
import type { AppLocale } from '@/i18n/routing';

interface OnboardingWizardProps {
  /**
   * member(기본): 완료 시 서버 저장 + 식단 생성 후 홈 이동 (FR-314)
   * guest: 서버 호출 없음 — 완료 시 onComplete(result) 로 결과만 반환 (게스트 체험 플로우)
   */
  mode?: 'member' | 'guest';
  /** 게스트 예산안 이전 성공 복귀 (?imported=1) — 확인 화면 후 STEP1 진입 (FR-108/315, member 전용) */
  imported?: boolean;
  /** guest 모드 완료 콜백 — 호출측(게스트 홈)이 적용 연출·스토어 저장 담당 */
  onComplete?: (result: OnboardingResult) => void;
  /** guest 모드 닫기 버튼 (오버레이 이탈) */
  onClose?: () => void;
}

type WizardStep = 0 | 1 | 2;

/** 완료 API 체크포인트 — 실패 시 해당 단계부터 재시도 (FR-314) */
type SubmitCheckpoint = 'household' | 'budget' | 'mealplan';
type SubmitError = SubmitCheckpoint | 'rate-limited';

/** 로캘 → 기본 통화 (KR ₩ / US $, api-spec 5-1) */
const LOCALE_CURRENCY: Record<AppLocale, Money['currency']> = {
  ko: 'KRW',
  en: 'USD',
};

/** 기본 가구 프리셋 — 신규 가입 기본 2인 (프리필 있으면 프리필 인원 우선) */
const DEFAULT_PRESET: PresetSize = 2;

function presetSizeFrom(size: number): PresetSize {
  if (size <= 1) return 1;
  if (size >= 5) return 5;
  return size as PresetSize;
}

/**
 * 온보딩 위저드 (ui-design 8장, FR-311~315) — 프로토타입 onboardStep 3스텝 1:1.
 * 완료: PUT households/me → PUT budget/plans → POST mealplans → 홈 (FR-314).
 */
export function OnboardingWizard({
  mode = 'member',
  imported = false,
  onComplete,
  onClose,
}: OnboardingWizardProps) {
  const t = useTranslations('onboarding');
  const tCuisine = useTranslations('cuisine');
  const locale = useLocale() as AppLocale;
  const router = useRouter();

  const currency = LOCALE_CURRENCY[locale] ?? 'KRW';

  const [intro, setIntro] = useState(mode === 'member' && imported);
  const [step, setStep] = useState<WizardStep>(0);
  const [members, setMembers] = useState<WizardMember[]>(() => buildPresetMembers(DEFAULT_PRESET));
  const [budget, setBudget] = useState<number | null>(null);
  const [locked, setLocked] = useState(true);
  const [cuisines, setCuisines] = useState<Cuisine[]>([]);
  const [direction, setDirection] = useState<MealDirection>('health');
  const [submitting, setSubmitting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [submitError, setSubmitError] = useState<SubmitError | null>(null);

  const nextIdRef = useRef(DEFAULT_PRESET + 1);
  const checkpointRef = useRef<SubmitCheckpoint>('household');
  const prefillBudgetRef = useRef<number | null>(null);

  // FR-315: 게스트 이전값 프리필 (스킵이 아닌 프리필 — 락·조정 기회 제공, member 전용)
  useEffect(() => {
    if (mode !== 'member') return;
    const prefill = readOnboardingPrefill();
    if (prefill === null) return;
    if (prefill.members !== undefined && prefill.members.length > 0) {
      // 게스트 위저드 확장분 — 구성원 유형·나이 그대로 복원
      setMembers(
        prefill.members.map((member, index) => ({
          id: index + 1,
          type: member.memberType,
          age: member.age,
        })),
      );
      nextIdRef.current = prefill.members.length + 1;
    } else {
      const size = presetSizeFrom(prefill.householdSize);
      setMembers(buildPresetMembers(size));
      nextIdRef.current = size + 1;
    }
    setDirection(prefill.mealDirection);
    if (prefill.cuisines !== undefined) setCuisines(prefill.cuisines);
    if (prefill.locked !== undefined) setLocked(prefill.locked);
    if (prefill.currency === currency) {
      prefillBudgetRef.current = Number.parseInt(prefill.amount, 10);
    }
  }, [mode, currency]);

  const applyPreset = useCallback((size: PresetSize) => {
    const preset = buildPresetMembers(size, 1);
    setMembers(preset);
    nextIdRef.current = size + 1;
  }, []);

  const addMember = useCallback((type: HouseholdMemberType) => {
    setMembers((current) => {
      if (!canAddMember(current)) return current;
      const id = nextIdRef.current;
      nextIdRef.current += 1;
      return [...current, { id, type, age: MEMBER_TYPES[type].defaultAge }];
    });
  }, []);

  const removeMember = useCallback((id: number) => {
    setMembers((current) =>
      canRemoveMember(current) ? current.filter((member) => member.id !== id) : current,
    );
  }, []);

  const changeAge = useCallback((id: number, delta: 1 | -1) => {
    setMembers((current) =>
      current.map((member) => {
        if (member.id !== id || !canChangeAge(member, delta)) return member;
        return { ...member, age: member.age + delta };
      }),
    );
  }, []);

  const size = members.length;

  // STEP2 진입 시 예산 확정: 프리필 → 클램프, 없으면 권장값 (FR-312/315)
  const goBudgetStep = useCallback(() => {
    setBudget((current) => {
      const base = current ?? prefillBudgetRef.current ?? budgetRange(size, currency).rec;
      return clampBudget(base, size, currency);
    });
    setStep(1);
  }, [size, currency]);

  const toggleCuisine = useCallback((cuisine: Cuisine) => {
    setCuisines((current) =>
      current.includes(cuisine)
        ? current.filter((existing) => existing !== cuisine)
        : [...current, cuisine],
    );
  }, []);

  // FR-314: household → budget → mealplan 순차 저장, 실패 체크포인트부터 재시도
  // guest 모드: 서버 호출 없이 onComplete 로 결과 반환 (적용 연출은 호출측)
  const submit = useCallback(async () => {
    if (submitting) return;
    const amount = String(budget ?? budgetRange(size, currency).rec);

    if (mode === 'guest') {
      onComplete?.({
        members: members.map((member) => ({ memberType: member.type, age: member.age })),
        householdSize: size,
        amount,
        currency,
        locked,
        cuisines,
        mealDirection: direction,
      });
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const fail = (kind: SubmitError) => {
      setSubmitError(kind);
      setGenerating(false);
      setSubmitting(false);
    };

    if (checkpointRef.current === 'household') {
      const result = await putHouseholdMembers(
        members.map((member) => ({ memberType: member.type, age: member.age })),
      );
      if (!result.ok) {
        fail('household');
        return;
      }
      checkpointRef.current = 'budget';
    }

    if (checkpointRef.current === 'budget') {
      const result = await putBudgetPlan({
        householdSize: size,
        budget: { amount, currency },
        mealDirection: direction,
        locked,
        cuisines,
      });
      if (!result.ok) {
        fail('budget');
        return;
      }
      checkpointRef.current = 'mealplan';
    }

    // 선호 음식은 로캘 라벨로 preferences 전달 (FR-314)
    setGenerating(true);
    const result = await createMealPlan({
      days: MEALPLAN_DAYS_DEFAULT,
      mealsPerDay: MEALPLAN_MEALS_PER_DAY,
      allergies: [],
      preferences: cuisines.map((cuisine) => tCuisine(cuisine)),
    });
    if (!result.ok) {
      fail(result.status === 429 ? 'rate-limited' : 'mealplan');
      return;
    }

    clearOnboardingPrefill();
    router.replace('/');
  }, [
    submitting,
    mode,
    onComplete,
    members,
    size,
    budget,
    currency,
    direction,
    locked,
    cuisines,
    tCuisine,
    router,
  ]);

  if (intro) {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col items-center justify-center gap-4 bg-white px-[22px] text-center sm:my-6 sm:min-h-[640px] sm:rounded-[32px] sm:shadow-card">
        <span
          aria-hidden
          className="flex h-[52px] w-[52px] items-center justify-center rounded-2xl bg-mint-50 text-[22px]"
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path
              d="M5 13l4 4 10-11"
              stroke="#0A8A60"
              strokeWidth="2.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <h1 className="text-xl font-extrabold tracking-tight text-navy-900">
          {t('imported.title')}
        </h1>
        <p className="text-sm leading-relaxed text-ink-500">{t('imported.description')}</p>
        <button
          type="button"
          onClick={() => setIntro(false)}
          className="mt-2 w-full rounded-2xl bg-brand-600 px-4 py-[17px] text-base font-bold text-white shadow-cta"
        >
          {t('imported.continueCta')}
        </button>
      </main>
    );
  }

  const errorBanner =
    submitError !== null ? (
      <div
        role="alert"
        className="mb-3.5 flex flex-col gap-2 rounded-2xl border border-flame-200 bg-white p-4 shadow-card"
      >
        <p className="text-[13px] font-semibold text-ink-600">
          {submitError === 'rate-limited' ? t('error.rateLimited') : t(`error.${submitError}`)}
        </p>
        <button
          type="button"
          disabled={submitting}
          onClick={() => void submit()}
          className="self-start rounded-xl bg-brand-600 px-4 py-2 text-xs font-extrabold text-white disabled:opacity-60"
        >
          {t('error.retry')}
        </button>
      </div>
    ) : null;

  const stepContent = (
    <>
      {step === 2 ? errorBanner : null}
      {step === 0 ? (
        <MemberStep
          members={members}
          onPreset={applyPreset}
          onAdd={addMember}
          onRemove={removeMember}
          onChangeAge={changeAge}
          onNext={goBudgetStep}
        />
      ) : null}
      {step === 1 && budget !== null ? (
        <BudgetStep
          size={size}
          budget={budget}
          currency={currency}
          locked={locked}
          onBudgetChange={(value) => setBudget(clampBudget(value, size, currency))}
          onToggleLock={() => setLocked((current) => !current)}
          onPrev={() => setStep(0)}
          onNext={() => setStep(2)}
        />
      ) : null}
      {step === 2 ? (
        <PreferenceStep
          cuisines={cuisines}
          direction={direction}
          submitting={submitting}
          onToggleCuisine={toggleCuisine}
          onSelectDirection={setDirection}
          onPrev={() => setStep(1)}
          onSubmit={() => void submit()}
        />
      ) : null}
    </>
  );

  if (mode === 'guest') {
    // 게스트 체험 플로우 — 전체 화면 오버레이 (BudgetDraftFlow 대체, 서버 호출 없음)
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('guestLabel')}
        className="fixed inset-0 z-50 overflow-y-auto bg-white"
      >
        <div className="relative mx-auto flex min-h-full w-full max-w-[480px] flex-col px-[22px] pb-[30px] pt-14">
          {onClose !== undefined ? (
            <button
              type="button"
              aria-label={t('closeLabel')}
              onClick={onClose}
              className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-xl bg-[#F0F2F6]"
            >
              <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path d="M6 6l12 12M18 6L6 18" stroke="#5B6B8C" strokeWidth="2.4" strokeLinecap="round" />
              </svg>
            </button>
          ) : null}
          {stepContent}
        </div>
      </div>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-[480px] flex-col bg-white px-[22px] pb-[30px] pt-14 sm:my-6 sm:min-h-[720px] sm:rounded-[32px] sm:shadow-card">
      {stepContent}

      {/* 저장 중 오버레이 (household/budget 단계) */}
      {submitting && !generating ? (
        <div
          role="status"
          aria-busy="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-surface/85 text-sm font-bold text-navy-900 backdrop-blur-sm"
        >
          {t('saving')}
        </div>
      ) : null}
      {/* 식단 생성 로딩 재사용 (FR-314) */}
      {generating ? <GenerationLoading /> : null}
    </main>
  );
}
