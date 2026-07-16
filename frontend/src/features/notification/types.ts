/**
 * notification 도메인 API 타입 — docs/설계/api-spec.md 6-A(v1.5)와 1:1 일치 (camelCase).
 */

/** 식사 리마인더 3종 (아침/점심/저녁) */
export type ReminderType =
  | 'meal_reminder_breakfast'
  | 'meal_reminder_lunch'
  | 'meal_reminder_dinner';

/** 알림 유형 — weekly_nudge 는 P2 (스키마만 선확정, UI 미노출) */
export type NotificationType = ReminderType | 'mealplan_done' | 'weekly_nudge';

/** GET/PUT /notifications/settings 의 설정 행 (api-spec 6-A-3) */
export interface NotificationSetting {
  type: NotificationType;
  enabled: boolean;
  /** HH:MM — 리마인더 3종만, 그 외 null */
  localTime: string | null;
  /** IANA 타임존 — 리마인더 3종만, 그 외 null */
  timezone: string | null;
}

/** 200 NotificationSettingsResponse (api-spec 6-A-3/6-A-4) */
export interface NotificationSettingsResponse {
  settings: NotificationSetting[];
}

/** PUT /notifications/settings 부분 갱신 항목 — 보낸 type 만 반영 (api-spec 6-A-4) */
export interface NotificationSettingUpdate {
  type: NotificationType;
  enabled?: boolean;
  localTime?: string;
  timezone?: string;
}

/** PUT /notifications/devices 요청 (api-spec 6-A-1) */
export interface DeviceRegisterRequest {
  token: string;
  platform: 'ios' | 'android';
  locale: 'ko' | 'en';
  timezone: string;
  appVersion: string;
}

/** 200 { id } (api-spec 6-A-1) */
export interface DeviceRegisterResponse {
  id: string;
}
