'use client';

import { useTranslations } from 'next-intl';
import {
  MEMBER_TYPES,
  MEMBER_TYPE_ORDER,
  PRESET_SIZES,
  type PresetSize,
} from '@/features/household/constants';
import {
  canAddMember,
  canChangeAge,
  canRemoveMember,
  type WizardMember,
} from '@/features/household/onboardingLogic';
import type { HouseholdMemberType } from '@/features/household/types';

interface MemberStepProps {
  members: WizardMember[];
  onPreset: (size: PresetSize) => void;
  onAdd: (type: HouseholdMemberType) => void;
  onRemove: (id: number) => void;
  onChangeAge: (id: number, delta: 1 | -1) => void;
  onNext: () => void;
}

/**
 * STEP 1/3 — 가구 구성원 설정 (FR-311, 프로토타입 onboardStep 0 재현).
 * 프리셋(1~5인) + 구성원 카드(모노그램·나이 스테퍼·삭제) + 유형별 추가.
 */
export function MemberStep({
  members,
  onPreset,
  onAdd,
  onRemove,
  onChangeAge,
  onNext,
}: MemberStepProps) {
  const t = useTranslations('onboarding');
  const tType = useTranslations('memberType');
  const count = members.length;
  const removable = canRemoveMember(members);
  const addable = canAddMember(members);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-5 flex items-center gap-2.5">
        <span
          aria-hidden
          className="flex h-[30px] w-[30px] items-center justify-center rounded-[9px] bg-navy-800 text-[11px] font-extrabold tracking-tight text-white"
        >
          GB
        </span>
        <span aria-hidden className="text-[15px] font-extrabold tracking-tight text-navy-900">
          JARIN<span className="text-brand-600">GO BE</span>
        </span>
      </div>
      <p className="mb-2 text-xs font-extrabold tracking-wider text-brand-600">
        {t('stepIndicator', { current: 1 })}
      </p>
      <h1 className="text-[27px] font-extrabold leading-tight tracking-tight text-navy-900">
        {t('step1.title1')}
        <br />
        {t('step1.title2')}
      </h1>
      <p className="mt-2 text-sm font-medium text-ink-400">{t('step1.subtitle')}</p>

      {/* N인 가구 칩 + 자동 계산 안내 */}
      <div className="mb-2.5 mt-[18px] flex items-center justify-between">
        <span className="inline-flex items-center gap-[7px] rounded-full bg-brand-50 px-3.5 py-[7px] text-[13px] font-extrabold text-brand-700">
          <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="8" r="3" stroke="#2453D6" strokeWidth="2" />
            <path d="M3.5 19a5.5 5.5 0 0 1 11 0" stroke="#2453D6" strokeWidth="2" strokeLinecap="round" />
            <path
              d="M16 5.5a3 3 0 0 1 0 5M17 19a5.5 5.5 0 0 0-2.5-4.6"
              stroke="#2453D6"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          {t('step1.householdChip', { count })}
        </span>
        <span className="text-xs font-semibold text-ink-300">{t('step1.memberHint')}</span>
      </div>

      {/* 1~5인 빠른 선택 */}
      <p className="mb-[7px] text-xs font-bold text-ink-400">{t('step1.quickSelect')}</p>
      <div className="mb-4 flex gap-[7px]">
        {PRESET_SIZES.map((size) => {
          const active = count === size;
          return (
            <button
              key={size}
              type="button"
              aria-pressed={active}
              onClick={() => onPreset(size)}
              className={`flex-1 rounded-[11px] py-[9px] text-center text-[13px] font-extrabold ${
                active ? 'bg-navy-800 text-white' : 'bg-[#F0F2F6] text-ink-500'
              }`}
            >
              {t('step1.presetLabel', { count: size })}
            </button>
          );
        })}
      </div>

      {/* 구성원 카드 리스트 */}
      <p className="mb-2 text-xs font-bold text-ink-400">
        {t('step1.memberList')} · {t('step1.householdBadge', { count })}
      </p>
      <ul className="flex min-h-0 flex-1 flex-col gap-[9px] overflow-y-auto">
        {members.map((member) => {
          const config = MEMBER_TYPES[member.type];
          const label = tType(`${member.type}.label`);
          const decAllowed = canChangeAge(member, -1);
          const incAllowed = canChangeAge(member, 1);
          return (
            <li
              key={member.id}
              className="flex items-center gap-[11px] rounded-2xl bg-[#F6F8FC] px-[13px] py-[11px]"
            >
              <span
                aria-hidden
                className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-[13px] text-base font-extrabold text-white"
                style={{ backgroundColor: config.color }}
              >
                {tType(`${member.type}.mono`)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14.5px] font-bold text-ink-800">{label}</p>
                <p className="text-[11.5px] text-ink-300">
                  {t('step1.ageWord')} ·{' '}
                  {t('step1.ageRange', { min: config.minAge, max: config.maxAge })}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-[7px]">
                <button
                  type="button"
                  aria-label={t('step1.decreaseAge', { name: label })}
                  disabled={!decAllowed}
                  onClick={() => onChangeAge(member.id, -1)}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#E1E6EF] bg-white disabled:opacity-35"
                >
                  <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none">
                    <path d="M6 12h12" stroke="#5B6B8C" strokeWidth="2.4" strokeLinecap="round" />
                  </svg>
                </button>
                <span className="min-w-[46px] text-center text-sm font-extrabold tabular-nums text-ink-800">
                  {t('step1.age', { age: member.age })}
                </span>
                <button
                  type="button"
                  aria-label={t('step1.increaseAge', { name: label })}
                  disabled={!incAllowed}
                  onClick={() => onChangeAge(member.id, 1)}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#E1E6EF] bg-white disabled:opacity-35"
                >
                  <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none">
                    <path d="M12 6v12M6 12h12" stroke="#2F6BFF" strokeWidth="2.4" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
              {removable ? (
                <button
                  type="button"
                  aria-label={t('step1.removeMember', { name: label })}
                  onClick={() => onRemove(member.id)}
                  className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] border border-[#F0DAD6] bg-white"
                >
                  <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none">
                    <path d="M6 6l12 12M18 6L6 18" stroke="#C2453A" strokeWidth="2.4" strokeLinecap="round" />
                  </svg>
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>

      {/* 구성원 추가 (유형별) */}
      <p className="mb-0.5 mt-1.5 text-xs font-bold text-ink-400">{t('step1.addMember')}</p>
      <div className="mt-1.5 flex flex-wrap gap-[7px]">
        {MEMBER_TYPE_ORDER.map((type) => (
          <button
            key={type}
            type="button"
            disabled={!addable}
            onClick={() => onAdd(type)}
            className="inline-flex items-center gap-[7px] rounded-full border-[1.5px] border-[#E1E6EF] bg-white px-[13px] py-2 text-[12.5px] font-bold text-ink-800 disabled:opacity-40"
          >
            <span
              aria-hidden
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: MEMBER_TYPES[type].color }}
            />
            {t('step1.addType', { name: tType(`${type}.label`) })}
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={onNext}
        className="mt-3.5 rounded-2xl bg-navy-800 py-[17px] text-center text-base font-bold text-white shadow-[0_10px_24px_rgba(21,36,74,.28)]"
      >
        {t('step1.next')}
      </button>
    </div>
  );
}
