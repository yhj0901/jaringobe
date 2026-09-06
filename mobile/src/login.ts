import * as WebBrowser from 'expo-web-browser';
import { parseDeepLink, type DeepLink } from './deeplink';
import type { LoginProvider } from './bridge';

/**
 * 소셜 로그인 커스텀 탭 (docs/설계/mobile-app.md 2장 login.ts)
 * 구글 웹뷰 차단 정책 대응 — 전 provider 를 커스텀 탭/시스템 브라우저에서 진행 (FR-009).
 * 완료 시 `jaringobe://auth?code=&next=` 복귀 → 웹뷰를 /auth/app/session 으로 내비게이트 (api-spec 1-6).
 */

const AUTH_RETURN_SCHEME = 'jaringobe://auth';

/** authorize URL — client=app 이면 콜백에서 쿠키 대신 원타임 코드 발급 (api-spec 1-1 v1.5) */
export function buildAuthorizeUrl(webUrl: string, provider: LoginProvider, next: string): string {
  return `${webUrl}/api/v1/auth/${provider}/authorize?client=app&next=${encodeURIComponent(next)}`;
}

/**
 * 커스텀 탭 오픈 → 복귀 딥링크 파싱.
 * 사용자가 탭을 닫는 등 복귀 URL 이 없으면 null (웹뷰 변화 없음 — 로그인 화면 유지).
 */
export async function openLoginTab(
  webUrl: string,
  provider: LoginProvider,
  next: string,
): Promise<DeepLink | null> {
  const result = await WebBrowser.openAuthSessionAsync(
    buildAuthorizeUrl(webUrl, provider, next),
    AUTH_RETURN_SCHEME,
  );
  if (result.type === 'success') {
    return parseDeepLink(result.url);
  }
  return null;
}
