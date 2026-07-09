import { describe, expect, it } from 'vitest';
import {
  buildAuthorizeUrl,
  providerOrder,
  sanitizeNextPath,
} from '@/features/auth/authorizeUrl';

describe('providerOrder (FR-007)', () => {
  it('ko 는 카카오 → 구글 순서다', () => {
    expect(providerOrder('ko')).toEqual(['kakao', 'google']);
  });

  it('en 은 구글 우선, 카카오 최하단이다', () => {
    expect(providerOrder('en')).toEqual(['google', 'kakao']);
  });
});

describe('sanitizeNextPath (CWE-601 클라이언트 위생)', () => {
  it('상대 경로만 허용한다', () => {
    expect(sanitizeNextPath('/')).toBe('/');
    expect(sanitizeNextPath('/onboarding')).toBe('/onboarding');
  });

  it('절대 URL·프로토콜 상대 URL·빈 값은 / 로 대체한다', () => {
    expect(sanitizeNextPath('https://evil.example')).toBe('/');
    expect(sanitizeNextPath('//evil.example')).toBe('/');
    expect(sanitizeNextPath(undefined)).toBe('/');
    expect(sanitizeNextPath('')).toBe('/');
  });
});

describe('buildAuthorizeUrl (api-spec 1-1)', () => {
  it('provider 경로와 인코딩된 next 를 조합한다', () => {
    expect(buildAuthorizeUrl('kakao', '/')).toBe('/api/v1/auth/kakao/authorize?next=%2F');
    expect(buildAuthorizeUrl('google', '/onboarding')).toBe(
      '/api/v1/auth/google/authorize?next=%2Fonboarding',
    );
  });

  it('위험한 next 는 / 로 대체된다', () => {
    expect(buildAuthorizeUrl('google', 'https://evil.example')).toBe(
      '/api/v1/auth/google/authorize?next=%2F',
    );
  });
});
