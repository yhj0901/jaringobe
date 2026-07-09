/**
 * 전역 상수 — 타이밍/보관 정책은 여기서만 조정한다 (FR-102 상수 분리 요구).
 */

/** 프롬프트 노출 전 체류(가시 상태 누적) 시간 */
export const PROMPT_DWELL_MS = 10_000;

/** 스크롤 유휴 판정 시간 — 스크롤 조작 중 노출 금지 (FR-102) */
export const SCROLL_IDLE_MS = 1_500;

/** 체류/유휴 판정 틱 간격 */
export const PROMPT_TICK_MS = 250;

/** 게스트 데이터 localStorage 보관 기간 (FR-107: 30일) */
export const GUEST_TTL_MS = 30 * 24 * 60 * 60 * 1_000;

/** zustand persist 키 (스키마 버전 포함) */
export const GUEST_STORAGE_KEY = 'jaringobe.guest.v1';

/** 게스트 스토어 스키마 버전 */
export const GUEST_SCHEMA_VERSION = 1;

/** 세션 내 프롬프트 노출/거절 플래그 (sessionStorage) */
export const PROMPT_SHOWN_SESSION_KEY = 'jaringobe.guest.promptShown';
export const PROMPT_DECLINED_SESSION_KEY = 'jaringobe.guest.promptDeclined';

/** 로그인 이력 마커 (localStorage) — 재방문 게스트 [로그인/구경] 알림 판정 (FR-316, ui-design 8장) */
export const VISITED_MARKER_KEY = 'jaringobe.visited';

/** 재방문 알림 세션 내 1회 노출 플래그 (sessionStorage, FR-316) */
export const REVISIT_SHOWN_SESSION_KEY = 'jaringobe.guest.revisitShown';

/** 게스트 이전 직후 온보딩 STEP2 프리필 전달 (sessionStorage, FR-315) */
export const ONBOARDING_PREFILL_SESSION_KEY = 'jaringobe.onboarding.prefill';

/** 가구 인원 입력 범위 (FR-104, api-spec 서버 검증과 동일) */
export const HOUSEHOLD_MIN = 1;
export const HOUSEHOLD_MAX = 10;

/** 예산 입력 허용 범위 (api-spec 2-1 서버 검증과 동일 — CWE-20) */
export const BUDGET_RANGE = {
  KRW: { min: 50_000, max: 5_000_000 },
  USD: { min: 50, max: 5_000 },
} as const;

/** 로캘별 월 예산 프리셋 (금액은 문자열 — float 금지) */
export const BUDGET_PRESETS = {
  ko: {
    currency: 'KRW',
    amounts: ['300000', '500000', '700000', '1000000'],
  },
  en: {
    currency: 'USD',
    amounts: ['300', '500', '700', '1000'],
  },
} as const;

/** 인증 httpOnly 쿠키 이름 (api-spec 0장) — 홈 라우트의 회원/게스트 데이터 소스 판정용 */
export const AUTH_COOKIE_NAMES = ['jaringobe_access', 'jaringobe_refresh'] as const;

/** api-spec 에 정의된 auth 에러/공통 에러 코드 — i18n 매핑 허용 목록 */
export const KNOWN_ERROR_CODES = [
  'AUTH_PROVIDER_DENIED',
  'AUTH_INVALID_STATE',
  'AUTH_PROVIDER_ERROR',
  'AUTH_REQUIRED',
  'AUTH_TOKEN_REVOKED',
  'FORBIDDEN_ORIGIN',
  'VALIDATION_ERROR',
  'RATE_LIMITED',
  'BUDGET_PLAN_EXISTS',
  'PROVIDER_NOT_SUPPORTED',
] as const;

/** 알려진 notice 코드 (api-spec 1-2) */
export const KNOWN_NOTICE_CODES = ['AUTH_EMAIL_CONFLICT_NOTICE'] as const;
