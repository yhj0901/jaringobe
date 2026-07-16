/**
 * 딥링크 파서 (docs/설계/mobile-app.md 6장) — 순수 함수 (단위 테스트 대상).
 * `jaringobe://auth?code=&next=` / `jaringobe://auth?error=` 와 푸시 data.path 화이트리스트.
 */

export interface AuthSuccessLink {
  kind: 'auth-success';
  code: string;
  next: string;
}

export interface AuthErrorLink {
  kind: 'auth-error';
  error: string;
}

export type DeepLink = AuthSuccessLink | AuthErrorLink;

/** 딥링크 에러 코드 폴백 — 형식 위반 값은 기존 로그인 에러 배너 재사용 (api-spec 1-2) */
const FALLBACK_ERROR_CODE = 'AUTH_PROVIDER_ERROR';

/**
 * 내부 상대경로 화이트리스트 (CWE-601) — `/` 시작 상대경로만 허용, 실패 시 홈 `/`.
 * 푸시 `data.path` 와 딥링크 `next` 공용.
 */
export function sanitizeInternalPath(path: unknown): string {
  if (typeof path !== 'string' || path.length === 0) return '/';
  if (!path.startsWith('/') || path.startsWith('//')) return '/'; // 프로토콜 상대 URL 차단
  if (path.includes('://') || path.includes('\\')) return '/'; // 절대 URL/이스케이프 차단
  return path;
}

/** 쿼리 문자열 → 파라미터 맵 (RN 환경 URL 폴리필 의존 없이 직접 파싱) */
function parseQuery(query: string): Record<string, string> {
  const params: Record<string, string> = {};
  for (const pair of query.split('&')) {
    if (pair === '') continue;
    const separator = pair.indexOf('=');
    const rawKey = separator === -1 ? pair : pair.slice(0, separator);
    const rawValue = separator === -1 ? '' : pair.slice(separator + 1);
    try {
      params[decodeURIComponent(rawKey)] = decodeURIComponent(rawValue);
    } catch {
      // 잘못된 인코딩 파라미터는 무시
    }
  }
  return params;
}

/**
 * `jaringobe://auth` 딥링크 파싱 — 그 외 스킴/호스트는 null (무시).
 * code 가 있으면 auth-success, 없으면 auth-error (코드 형식 검증 포함).
 */
export function parseDeepLink(url: string): DeepLink | null {
  const match = /^jaringobe:\/\/auth\/?(?:\?(.*))?$/.exec(url);
  if (match === null) return null;
  const params = parseQuery(match[1] ?? '');

  const code = params.code;
  if (typeof code === 'string' && code.length > 0) {
    return { kind: 'auth-success', code, next: sanitizeInternalPath(params.next) };
  }

  const error = params.error;
  const safeError =
    typeof error === 'string' && /^[A-Z0-9_]{1,64}$/.test(error) ? error : FALLBACK_ERROR_CODE;
  return { kind: 'auth-error', error: safeError };
}

/**
 * 딥링크 → 웹뷰 내비게이트 대상 URL (mobile-app 6장)
 * auth-success → `/api/v1/auth/app/session?code=&next=` (쿠키 인계, api-spec 1-6)
 * auth-error   → `/login?error={code}` (기존 에러 배너 재사용)
 */
export function resolveDeepLinkUrl(webUrl: string, link: DeepLink): string {
  if (link.kind === 'auth-success') {
    return `${webUrl}/api/v1/auth/app/session?code=${encodeURIComponent(link.code)}&next=${encodeURIComponent(link.next)}`;
  }
  return `${webUrl}/login?error=${encodeURIComponent(link.error)}`;
}

/** 푸시 data.path → 웹뷰 URL — 화이트리스트 검증 후 결합, 실패 시 홈 (mobile-app 5장) */
export function pushPathToUrl(webUrl: string, path: unknown): string {
  return `${webUrl}${sanitizeInternalPath(path)}`;
}
