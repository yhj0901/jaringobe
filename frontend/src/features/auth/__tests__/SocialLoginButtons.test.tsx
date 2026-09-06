import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { SocialLoginButtons } from '@/features/auth/SocialLoginButtons';
import { renderWithIntl } from '@/test/renderWithIntl';
import { stubAppEnvironment } from '@/test/appEnv';

describe('SocialLoginButtons (FR-001/007)', () => {
  const originalLocation = window.location;

  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, href: 'http://localhost/' },
      writable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
      writable: true,
    });
  });

  it('ko 로캘: 카카오가 첫 번째, 구글이 두 번째다', () => {
    renderWithIntl(<SocialLoginButtons next="/" />, 'ko');
    const buttons = screen.getAllByRole('button');
    expect(buttons[0]).toHaveTextContent('카카오로 시작하기');
    expect(buttons[1]).toHaveTextContent('구글로 시작하기');
    // 애플은 P1 — 미노출
    expect(screen.queryByText('애플로 시작하기')).not.toBeInTheDocument();
  });

  it('en 로캘: 구글 우선, 카카오 최하단이다', () => {
    renderWithIntl(<SocialLoginButtons next="/" />, 'en');
    const buttons = screen.getAllByRole('button');
    expect(buttons[0]).toHaveTextContent('Continue with Google');
    expect(buttons[buttons.length - 1]).toHaveTextContent('Continue with Kakao');
  });

  it('버튼 클릭 시 authorize 엔드포인트로 브라우저 내비게이션한다 (api-spec 1-1)', () => {
    renderWithIntl(<SocialLoginButtons next="/" />, 'ko');
    fireEvent.click(screen.getByRole('button', { name: '카카오로 시작하기' }));
    expect(window.location.href).toBe('/api/v1/auth/kakao/authorize?next=%2F');
  });

  it('next 미지정 시 기본 / 로 복귀한다', () => {
    renderWithIntl(<SocialLoginButtons />, 'ko');
    fireEvent.click(screen.getByRole('button', { name: '구글로 시작하기' }));
    expect(window.location.href).toBe('/api/v1/auth/google/authorize?next=%2F');
  });

  it('앱 내(isApp) → LOGIN_PROVIDER 브리지 메시지 전송, 브라우저 내비게이션 없음 (ui-design 12장)', () => {
    const app = stubAppEnvironment();
    try {
      renderWithIntl(<SocialLoginButtons next="/settings" />, 'ko');
      fireEvent.click(screen.getByRole('button', { name: '카카오로 시작하기' }));

      expect(app.postMessage).toHaveBeenCalledTimes(1);
      expect(JSON.parse(app.postMessage.mock.calls[0]?.[0] as string)).toEqual({
        v: 1,
        type: 'LOGIN_PROVIDER',
        payload: { provider: 'kakao', next: '/settings' },
      });
      expect(window.location.href).toBe('http://localhost/');
    } finally {
      app.restore();
    }
  });

  it('앱 내 next 위생 처리 — 외부 URL 은 / 로 대체 (CWE-601)', () => {
    const app = stubAppEnvironment();
    try {
      renderWithIntl(<SocialLoginButtons next="https://evil.example" />, 'ko');
      fireEvent.click(screen.getByRole('button', { name: '구글로 시작하기' }));
      expect(JSON.parse(app.postMessage.mock.calls[0]?.[0] as string).payload).toEqual({
        provider: 'google',
        next: '/',
      });
    } finally {
      app.restore();
    }
  });
});
