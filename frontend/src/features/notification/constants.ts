import type { ReminderType } from '@/features/notification/types';

/**
 * notification 도메인 상수 (ui-design 12장).
 */

/** 리마인더 행 표시 순서 (아침 → 점심 → 저녁) */
export const REMINDER_TYPES: readonly ReminderType[] = [
  'meal_reminder_breakfast',
  'meal_reminder_lunch',
  'meal_reminder_dinner',
];

/** 리마인더 기본 시각 — 서버 lazy 생성 기본값과 동일 (기획 FR-006), localTime null 폴백 */
export const REMINDER_DEFAULT_TIMES: Record<ReminderType, string> = {
  meal_reminder_breakfast: '08:00',
  meal_reminder_lunch: '12:00',
  meal_reminder_dinner: '18:30',
};

/** 푸시 soft ask 1회 노출 마커 (localStorage, FR-002 — 거부 후 재노출 금지) */
export const PUSH_SOFT_ASK_SHOWN_KEY = 'jaringobe.push.softAskShown';
