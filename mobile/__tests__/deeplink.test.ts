import {
  parseDeepLink,
  pushPathToUrl,
  resolveDeepLinkUrl,
  sanitizeInternalPath,
} from '../src/deeplink';

/**
 * 딥링크 파서·path 화이트리스트 단위 테스트 (mobile-app 8장 — jest-expo).
 * 실행: mobile/ 에서 `npm install` 후 `npm test` (네트워크 필요 — CI/로컬에서 실행).
 */

const WEB = 'https://jaringobe.cloud';

describe('sanitizeInternalPath — 내부 상대경로 화이트리스트 (CWE-601)', () => {
  it('`/` 시작 상대경로만 허용한다', () => {
    expect(sanitizeInternalPath('/mealplan/abc')).toBe('/mealplan/abc');
    expect(sanitizeInternalPath('/settings/notifications')).toBe('/settings/notifications');
  });

  it('외부 URL·프로토콜 상대·비문자열은 홈으로 폴백한다', () => {
    expect(sanitizeInternalPath('https://evil.example')).toBe('/');
    expect(sanitizeInternalPath('//evil.example')).toBe('/');
    expect(sanitizeInternalPath('/redirect?to=https://evil.example')).toBe('/'); // '://' 포함 차단
    expect(sanitizeInternalPath('javascript:alert(1)')).toBe('/');
    expect(sanitizeInternalPath('\\\\evil')).toBe('/');
    expect(sanitizeInternalPath('')).toBe('/');
    expect(sanitizeInternalPath(undefined)).toBe('/');
    expect(sanitizeInternalPath(42)).toBe('/');
  });
});

describe('parseDeepLink (jaringobe://auth, mobile-app 6장)', () => {
  it('code + next → auth-success (next 는 화이트리스트 검증)', () => {
    expect(parseDeepLink('jaringobe://auth?code=abc123&next=%2Fsettings')).toEqual({
      kind: 'auth-success',
      code: 'abc123',
      next: '/settings',
    });
    // 외부 next → '/'
    expect(parseDeepLink('jaringobe://auth?code=abc&next=https%3A%2F%2Fevil.example')).toEqual({
      kind: 'auth-success',
      code: 'abc',
      next: '/',
    });
  });

  it('error → auth-error, 형식 위반 코드는 AUTH_PROVIDER_ERROR 로 폴백', () => {
    expect(parseDeepLink('jaringobe://auth?error=AUTH_INVALID_APP_CODE')).toEqual({
      kind: 'auth-error',
      error: 'AUTH_INVALID_APP_CODE',
    });
    expect(parseDeepLink('jaringobe://auth?error=<script>')).toEqual({
      kind: 'auth-error',
      error: 'AUTH_PROVIDER_ERROR',
    });
    expect(parseDeepLink('jaringobe://auth')).toEqual({
      kind: 'auth-error',
      error: 'AUTH_PROVIDER_ERROR',
    });
  });

  it('다른 스킴/호스트는 null (무시)', () => {
    expect(parseDeepLink('https://jaringobe.cloud/auth?code=abc')).toBeNull();
    expect(parseDeepLink('jaringobe://other?code=abc')).toBeNull();
    expect(parseDeepLink('evil://auth?code=abc')).toBeNull();
  });
});

describe('resolveDeepLinkUrl — 웹뷰 내비게이트 대상 (api-spec 1-6)', () => {
  it('auth-success → /api/v1/auth/app/session?code=&next= (쿠키 인계)', () => {
    expect(
      resolveDeepLinkUrl(WEB, { kind: 'auth-success', code: 'a+b/c', next: '/mealplan/1' }),
    ).toBe(`${WEB}/api/v1/auth/app/session?code=a%2Bb%2Fc&next=%2Fmealplan%2F1`);
  });

  it('auth-error → /login?error={code} (기존 에러 배너 재사용)', () => {
    expect(resolveDeepLinkUrl(WEB, { kind: 'auth-error', error: 'AUTH_INVALID_APP_CODE' })).toBe(
      `${WEB}/login?error=AUTH_INVALID_APP_CODE`,
    );
  });
});

describe('pushPathToUrl — 푸시 data.path 라우팅 (mobile-app 5장)', () => {
  it('상대경로는 WEB_URL 과 결합, 위반 값은 홈으로', () => {
    expect(pushPathToUrl(WEB, '/mealplan/abc')).toBe(`${WEB}/mealplan/abc`);
    expect(pushPathToUrl(WEB, 'https://evil.example')).toBe(`${WEB}/`);
    expect(pushPathToUrl(WEB, undefined)).toBe(`${WEB}/`);
  });
});
