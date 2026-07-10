/**
 * mealplan 도메인 상수 — api-spec 3장 서버 검증과 동일 범위 (CWE-20 클라이언트 선검증).
 */

/** 식단 기간(days) 허용 범위 (api-spec 3-2: 1~31) */
export const MEALPLAN_DAYS_MIN = 1;
export const MEALPLAN_DAYS_MAX = 31;
/** 생성 시트 기본 기간 (FR-203: 기본 7일) */
export const MEALPLAN_DAYS_DEFAULT = 7;

/** 하루 끼니 수 — 이번 범위는 아침/점심/저녁 고정 3끼 (기획 FR-205) */
export const MEALPLAN_MEALS_PER_DAY = 3;

/** 알레르기/선호 항목당 최대 길이 (api-spec 3-2: 30자, CWE-79) */
export const PLAN_ITEM_MAX_LENGTH = 30;
/** 알레르기/선호 목록당 최대 개수 (api-spec 3-2: 10개) */
export const PLAN_ITEMS_MAX_COUNT = 10;

/** POST /mealplans · regenerate 클라이언트 타임아웃 (ui-design 7장: 90초) */
export const MEALPLAN_CREATE_TIMEOUT_MS = 90_000;

/** 생성 로딩 단계 문구 로테이션 간격 (FR-204) */
export const GENERATION_STEP_INTERVAL_MS = 2_500;

/** "준비 중" 안내 스낵바 자동 닫힘 시간 (FR-208) */
export const LOCKED_NOTICE_MS = 2_500;

/** latest 404 — 빈 상태 분기 전용 코드 (api-spec 3-1) */
export const MEALPLAN_NOT_FOUND_CODE = 'MEALPLAN_NOT_FOUND';

/** 레시피 시트 "N인분" 기본값 — 가구 인원 미조회 시 폴백 (FR-504) */
export const RECIPE_DEFAULT_SERVINGS = 2;

/** 레시피 시트 기본 조리 난이도 — difficulty 부재 시 (FR-505: "쉬움") */
export const RECIPE_DEFAULT_DIFFICULTY = 'easy' as const;
