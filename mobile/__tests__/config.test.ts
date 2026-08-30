import { isInternalUrl } from '../src/config';

/**
 * 내부 URL 판정 단위 테스트 (BUG-003 — 오리진 프리픽스 매칭 우회, CWE-345/601).
 * 실행: mobile/ 에서 `npm install` 후 `npm test`.
 */

const WEB_URL = 'https://jaringobe.cloud';

describe('isInternalUrl — 오리진 완전 일치만 내부 허용 (BUG-003)', () => {
  it('동일 오리진(루트/경로/쿼리/해시)은 내부', () => {
    expect(isInternalUrl('https://jaringobe.cloud', WEB_URL)).toBe(true);
    expect(isInternalUrl('https://jaringobe.cloud/', WEB_URL)).toBe(true);
    expect(isInternalUrl('https://jaringobe.cloud/ko/settings', WEB_URL)).toBe(true);
    expect(isInternalUrl('https://jaringobe.cloud/ko?tab=push#top', WEB_URL)).toBe(true);
  });

  it('QA 재현 케이스: 프리픽스 매칭 우회 도메인은 외부 (CWE-345)', () => {
    // 구현이 startsWith(WEB_URL) 이면 통과해 버리는 공격 URL — 반드시 false
    expect(isInternalUrl('https://jaringobe.cloud.evil.com', WEB_URL)).toBe(false);
    expect(isInternalUrl('https://jaringobe.cloud.evil.com/phish', WEB_URL)).toBe(false);
  });

  it('서브도메인/유사 호스트/userinfo 트릭은 외부', () => {
    expect(isInternalUrl('https://evil.jaringobe.cloud', WEB_URL)).toBe(false);
    expect(isInternalUrl('https://jaringobe.cloud@evil.com/', WEB_URL)).toBe(false);
    expect(isInternalUrl('https://jaringobecloud.com', WEB_URL)).toBe(false);
  });

  it('스킴/포트가 다르면 외부 (오리진 불일치)', () => {
    expect(isInternalUrl('http://jaringobe.cloud/ko', WEB_URL)).toBe(false);
    expect(isInternalUrl('https://jaringobe.cloud:8443/ko', WEB_URL)).toBe(false);
  });

  it('파싱 실패·비 http(s) 스킴 URL 은 거부', () => {
    expect(isInternalUrl('not a url', WEB_URL)).toBe(false);
    expect(isInternalUrl('', WEB_URL)).toBe(false);
    expect(isInternalUrl('jaringobe://auth?code=x', WEB_URL)).toBe(false);
    expect(isInternalUrl('javascript:alert(1)', WEB_URL)).toBe(false);
    expect(isInternalUrl('about:blank', WEB_URL)).toBe(false);
  });

  it('기준 webUrl 자체가 파싱 불가하면 거부', () => {
    expect(isInternalUrl('https://jaringobe.cloud/ko', 'broken url')).toBe(false);
  });
});
