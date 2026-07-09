export type SocialProvider = 'kakao' | 'google' | 'apple';

/**
 * 로캘별 provider 노출 순서 (FR-007, ui-design 5장)
 * ko: 카카오 → 구글 / en: 구글 우선, 카카오 최하단.
 * 애플은 P1 — 어댑터/순서만 예약해 두고 버튼은 미노출.
 */
export function providerOrder(locale: string): SocialProvider[] {
  if (locale === 'ko') {
    // P1 적용 시: ['kakao', 'google', 'apple']
    return ['kakao', 'google'];
  }
  // P1 적용 시: ['google', 'apple', 'kakao']
  return ['google', 'kakao'];
}

/** next 파라미터는 자체 상대 경로만 허용 (CWE-601 클라이언트 위생 — 서버가 최종 검증) */
export function sanitizeNextPath(next: string | undefined): string {
  if (!next) return '/';
  if (!next.startsWith('/') || next.startsWith('//')) return '/';
  return next;
}

/** GET /api/v1/auth/{provider}/authorize?next=... (api-spec 1-1, 브라우저 내비게이션 전용) */
export function buildAuthorizeUrl(provider: SocialProvider, next: string | undefined): string {
  const safeNext = sanitizeNextPath(next);
  return `/api/v1/auth/${provider}/authorize?next=${encodeURIComponent(safeNext)}`;
}
