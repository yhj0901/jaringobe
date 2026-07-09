import { Suspense } from 'react';
import { cookies } from 'next/headers';
import { setRequestLocale } from 'next-intl/server';
import { GuestHomeController } from '@/features/guest/GuestHomeController';
import { MemberHomeController } from '@/features/mealplan/MemberHomeController';
import { PostLoginHandler } from '@/features/auth/PostLoginHandler';
import { AUTH_COOKIE_NAMES } from '@/shared/config/constants';

interface HomePageProps {
  params: { locale: string };
}

/**
 * 홈 (`/`) — 게스트/회원 공용 셸 (FR-101, ui-design 1장).
 * 회원 여부는 서버에서 인증 쿠키 존재로 판정해 데이터 소스를 결정한다:
 * - 쿠키 있음 → MemberHomeController (users/me → mealplans/latest 분기, FR-201)
 * - 쿠키 없음 → GuestHomeController (기존 게스트 동작 불변)
 * 세션 유효성은 서버 API 가 검증한다 — 쿠키가 무효(401)면 클라이언트에서 게스트로 폴백.
 */
export default function HomePage({ params: { locale } }: HomePageProps) {
  setRequestLocale(locale);

  const cookieStore = cookies();
  const maybeMember = AUTH_COOKIE_NAMES.some((name) => cookieStore.has(name));

  return (
    <>
      <Suspense fallback={null}>
        <PostLoginHandler />
      </Suspense>
      {maybeMember ? <MemberHomeController /> : <GuestHomeController />}
    </>
  );
}
