import createMiddleware from 'next-intl/middleware';
import { NextRequest, NextResponse } from 'next/server';
import { routing } from '@/i18n/routing';

const intlMiddleware = createMiddleware(routing);

/** 보호 라우트 (/onboarding + /settings) — 미인증 시 /login?next= 리다이렉트 (ui-design 1·9장) */
const PROTECTED_PATHS = ['/onboarding', '/settings'];

function stripLocale(pathname: string): string {
  const match = pathname.match(/^\/(ko|en)(\/.*)?$/);
  if (match) return match[2] ?? '/';
  return pathname;
}

export default function middleware(request: NextRequest): NextResponse {
  const pathname = stripLocale(request.nextUrl.pathname);
  const isProtected = PROTECTED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (isProtected) {
    const hasAccess = request.cookies.has('jaringobe_access');
    const hasRefresh = request.cookies.has('jaringobe_refresh');
    if (!hasAccess && !hasRefresh) {
      const url = request.nextUrl.clone();
      url.pathname = '/login';
      url.search = `?next=${encodeURIComponent(pathname)}`;
      return NextResponse.redirect(url);
    }
  }

  return intlMiddleware(request);
}

export const config = {
  // API/정적 리소스 제외 전 경로에 로캘 라우팅 적용
  matcher: ['/((?!api|_next|_vercel|.*\\..*).*)'],
};
