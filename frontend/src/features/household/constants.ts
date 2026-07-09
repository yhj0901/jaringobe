import type { Money } from '@/shared/api/types';
import type { Cuisine, HouseholdMemberType } from '@/features/household/types';

/**
 * 온보딩 3스텝 상수 — Claude Design 프로토타입(jaringobe-app-design, onboardStep)과 1:1.
 * 나이 범위·기본 나이는 api-spec 4-1 서버 재검증과 동일 (CWE-20 클라이언트 선검증).
 */

export interface MemberTypeConfig {
  /** 모노그램 배지 배경색 (프로토타입 MEMBER_TYPES.bg) */
  color: string;
  defaultAge: number;
  minAge: number;
  maxAge: number;
}

export const MEMBER_TYPES: Record<HouseholdMemberType, MemberTypeConfig> = {
  adult_m: { color: '#15244A', defaultAge: 35, minAge: 20, maxAge: 99 },
  adult_f: { color: '#2F6BFF', defaultAge: 33, minAge: 20, maxAge: 99 },
  teen: { color: '#0FB07A', defaultAge: 15, minAge: 13, maxAge: 19 },
  child: { color: '#F2A93B', defaultAge: 9, minAge: 7, maxAge: 12 },
  toddler: { color: '#E0651A', defaultAge: 4, minAge: 0, maxAge: 6 },
};

/** 구성원 추가 버튼 노출 순서 (프로토타입 ADD_ORDER) */
export const MEMBER_TYPE_ORDER: readonly HouseholdMemberType[] = [
  'adult_m',
  'adult_f',
  'teen',
  'child',
  'toddler',
];

export type PresetSize = 1 | 2 | 3 | 4 | 5;

/** 1~5인 가구 빠른 선택 프리셋 (프로토타입 PRESETS, FR-311) */
export const HOUSEHOLD_PRESETS: Record<PresetSize, readonly HouseholdMemberType[]> = {
  1: ['adult_m'],
  2: ['adult_m', 'adult_f'],
  3: ['adult_m', 'adult_f', 'child'],
  4: ['adult_m', 'adult_f', 'child', 'child'],
  5: ['adult_m', 'adult_f', 'child', 'child', 'toddler'],
};

export const PRESET_SIZES: readonly PresetSize[] = [1, 2, 3, 4, 5];

/** 1인당 월 예산 기준 (api-spec 5-1 프론트 상수 — KR ₩80,000/₩130,000/₩220,000 · US $60/$100/$170) */
export const BUDGET_PER_PERSON: Record<Money['currency'], { min: number; rec: number; max: number }> = {
  KRW: { min: 80_000, rec: 130_000, max: 220_000 },
  USD: { min: 60, rec: 100, max: 170 },
};

/** 예산 슬라이더 step (FR-312 — KRW 10,000 / USD 10) */
export const BUDGET_SLIDER_STEP: Record<Money['currency'], number> = {
  KRW: 10_000,
  USD: 10,
};

/** 수준 피드백 "적정" 상한 배수 — 권장 ×1.3 (정수 연산용 분수, float 금지) */
export const BUDGET_MOOD_RATIO = { num: 13, den: 10 } as const;

/** 선호 음식 6종 (api-spec 5-1 열거값, FR-313) */
export const CUISINE_IDS: readonly Cuisine[] = [
  'korean',
  'western',
  'japanese',
  'chinese',
  'comfort',
  'salad',
];

/** 음식 카드 썸네일 아트 (프로토타입 cuisineChips art 배열과 동일 순서) */
export const CUISINE_ART: Record<Cuisine, { gradient: string; color: string }> = {
  korean: { gradient: 'linear-gradient(135deg,#FDEEE9,#F7D3C6)', color: '#C2552F' },
  western: { gradient: 'linear-gradient(135deg,#FEF6E6,#FAE2B4)', color: '#B9771C' },
  japanese: { gradient: 'linear-gradient(135deg,#E9F1FF,#CCDEFB)', color: '#2F6BFF' },
  chinese: { gradient: 'linear-gradient(135deg,#FDEAEA,#F6C9C9)', color: '#C2453A' },
  comfort: { gradient: 'linear-gradient(135deg,#FBECF5,#F1D2E5)', color: '#B23A77' },
  salad: { gradient: 'linear-gradient(135deg,#E7F7EE,#CDEBD9)', color: '#0A8A60' },
};

/** 식단 방향 카드 아트 (프로토타입 focusCards art) */
export const DIRECTION_ART: Record<
  'health' | 'diet' | 'hearty' | 'kids',
  { gradient: string; color: string }
> = {
  health: { gradient: 'linear-gradient(135deg,#E7F7EE,#CDEBD9)', color: '#0A8A60' },
  diet: { gradient: 'linear-gradient(135deg,#E9F1FF,#CCDEFB)', color: '#2F6BFF' },
  hearty: { gradient: 'linear-gradient(135deg,#FEF6E6,#FAE2B4)', color: '#B9771C' },
  kids: { gradient: 'linear-gradient(135deg,#FBECF5,#F1D2E5)', color: '#B23A77' },
};

/** 예산 수준 피드백 배너 색 (프로토타입 mood 팔레트 — 알뜰/적정/여유) */
export const MOOD_ART: Record<'frugal' | 'moderate' | 'roomy', { color: string; bg: string }> = {
  frugal: { color: '#0A8A60', bg: '#E6F8F1' },
  moderate: { color: '#C2761F', bg: '#FEF3E2' },
  roomy: { color: '#C2453A', bg: '#FCEBEA' },
};
