'use client';

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { MemberStep } from '@/features/household/MemberStep';
import { BudgetStep } from '@/features/household/BudgetStep';
import { PreferenceStep } from '@/features/household/PreferenceStep';
import { MEMBER_TYPES, type PresetSize } from '@/features/household/constants';
import {
  budgetRange,
  buildPresetMembers,
  canAddMember,
  canChangeAge,
  canRemoveMember,
  clampBudget,
  type WizardMember,
} from '@/features/household/onboardingLogic';
import type { DietSection } from '@/features/settings/useSettings';
import type {
  Cuisine,
  HouseholdMemberInput,
  HouseholdMemberType,
} from '@/features/household/types';
import type { MealDirection, Money } from '@/shared/api/types';

/** 단일 편집 저장 페이로드 — 섹션별 판별 유니언 (FR-402) */
export type SettingsEditResult =
  | { section: 'household'; members: HouseholdMemberInput[] }
  | { section: 'budget'; amount: string; locked: boolean }
  | { section: 'preference'; cuisines: Cuisine[]; direction: MealDirection };

interface EditOverlayProps {
  section: DietSection;
  currency: Money['currency'];
  /** 현재 가구 구성 (null → 기본 2인 프리셋) — budget 스텝의 슬라이더 인원 기준으로도 사용 */
  initialMembers: HouseholdMemberInput[] | null;
  /** 현재 예산 금액 (mealplans/latest 요약) — null 이면 권장값 */
  initialBudget: Money | null;
  initialLocked: boolean;
  initialCuisines: Cuisine[];
  initialDirection: MealDirection;
  saving: boolean;
  saveError: boolean;
  onCancel: () => void;
  onSave: (result: SettingsEditResult) => void;
}

function toWizardMembers(members: HouseholdMemberInput[] | null): WizardMember[] {
  if (members === null || members.length === 0) return buildPresetMembers(2);
  return members.map((member, index) => ({
    id: index + 1,
    type: member.memberType,
    age: member.age,
  }));
}

/** Money 문자열("700000.00") → 슬라이더 정수 (클램프는 렌더 시 수행) */
function toBudgetNumber(budget: Money | null): number | null {
  if (budget === null) return null;
  const parsed = Number.parseInt(budget.amount, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * 설정 단일 편집 오버레이 (ui-design 9장, FR-402)
 * 온보딩 스텝 컴포넌트(MemberStep/BudgetStep/PreferenceStep)를 초기값 주입 + 저장/취소 라벨로 재사용.
 */
export function EditOverlay({
  section,
  currency,
  initialMembers,
  initialBudget,
  initialLocked,
  initialCuisines,
  initialDirection,
  saving,
  saveError,
  onCancel,
  onSave,
}: EditOverlayProps) {
  const t = useTranslations('settings.edit');

  const [members, setMembers] = useState<WizardMember[]>(() => toWizardMembers(initialMembers));
  const size = initialMembers?.length ?? 2;
  const [budget, setBudget] = useState<number>(() =>
    clampBudget(toBudgetNumber(initialBudget) ?? budgetRange(size, currency).rec, size, currency),
  );
  const [locked, setLocked] = useState(initialLocked);
  const [cuisines, setCuisines] = useState<Cuisine[]>(initialCuisines);
  const [direction, setDirection] = useState<MealDirection>(initialDirection);

  const nextIdRef = useRef(members.length + 1);

  const applyPreset = useCallback((presetSize: PresetSize) => {
    setMembers(buildPresetMembers(presetSize));
    nextIdRef.current = presetSize + 1;
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

  const submit = useCallback(() => {
    if (saving) return;
    if (section === 'household') {
      onSave({
        section,
        members: members.map((member) => ({ memberType: member.type, age: member.age })),
      });
    } else if (section === 'budget') {
      onSave({ section, amount: String(budget), locked });
    } else {
      onSave({ section, cuisines, direction });
    }
  }, [saving, section, members, budget, locked, cuisines, direction, onSave]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t('label')}
      className="fixed inset-0 z-50 overflow-y-auto bg-white"
    >
      <div className="relative mx-auto flex min-h-full w-full max-w-[480px] flex-col px-[22px] pb-[30px] pt-14">
        <button
          type="button"
          aria-label={t('closeLabel')}
          onClick={onCancel}
          className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-xl bg-[#F0F2F6]"
        >
          <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M6 6l12 12M18 6L6 18" stroke="#5B6B8C" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
        </button>

        {saveError ? (
          <div
            role="alert"
            className="mb-3.5 rounded-2xl border border-flame-200 bg-white p-4 text-[13px] font-semibold text-ink-600 shadow-card"
          >
            {t('saveFailed')}
          </div>
        ) : null}

        {section === 'household' ? (
          <MemberStep
            members={members}
            onPreset={applyPreset}
            onAdd={addMember}
            onRemove={removeMember}
            onChangeAge={changeAge}
            onNext={submit}
            nextLabel={t('save')}
          />
        ) : null}
        {section === 'budget' ? (
          <BudgetStep
            size={size}
            budget={budget}
            currency={currency}
            locked={locked}
            onBudgetChange={(value) => setBudget(clampBudget(value, size, currency))}
            onToggleLock={() => setLocked((current) => !current)}
            onPrev={onCancel}
            onNext={submit}
            prevLabel={t('cancel')}
            nextLabel={t('save')}
          />
        ) : null}
        {section === 'preference' ? (
          <PreferenceStep
            cuisines={cuisines}
            direction={direction}
            submitting={saving}
            onToggleCuisine={(cuisine) =>
              setCuisines((current) =>
                current.includes(cuisine)
                  ? current.filter((existing) => existing !== cuisine)
                  : [...current, cuisine],
              )
            }
            onSelectDirection={setDirection}
            onPrev={onCancel}
            onSubmit={submit}
            prevLabel={t('cancel')}
            ctaLabel={t('save')}
          />
        ) : null}

        {saving ? (
          <div
            role="status"
            aria-busy="true"
            className="fixed inset-0 z-50 flex items-center justify-center bg-surface/85 text-sm font-bold text-navy-900 backdrop-blur-sm"
          >
            {t('saving')}
          </div>
        ) : null}
      </div>
    </div>
  );
}
