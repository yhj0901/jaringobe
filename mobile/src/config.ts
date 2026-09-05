/**
 * 앱 설정 — WEB_URL 은 EAS 빌드 프로필 env(EXPO_PUBLIC_WEB_URL) 로 주입 (mobile-app 2·7장).
 * 시크릿 아님(공개 URL) — 자격증명은 EAS Secrets 로만 관리 (CWE-522).
 */

const DEFAULT_WEB_URL = 'https://jaringobe.cloud';

/** 웹뷰가 로드하는 자사 웹 오리진 — 내부 내비게이션 allowlist 기준 (mobile-app 4장) */
export const WEB_URL = (process.env.EXPO_PUBLIC_WEB_URL ?? DEFAULT_WEB_URL).replace(/\/+$/, '');

/**
 * 내부 URL 판정 — URL 파싱 후 오리진(스킴+호스트+포트) 완전 일치만 허용 (BUG-003, CWE-345/601).
 * 프리픽스 매칭(startsWith) 금지: `https://jaringobe.cloud.evil.com` 류 우회를 차단한다.
 * 파싱 실패 URL 은 거부(false).
 */
export function isInternalUrl(url: string, webUrl: string): boolean {
  try {
    return new URL(url).origin === new URL(webUrl).origin;
  } catch {
    return false; // 파싱 불가 URL 은 내부로 취급하지 않음
  }
}
