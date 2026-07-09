import { Suspense } from 'react';
import { setRequestLocale } from 'next-intl/server';
import { GuestHomeController } from '@/features/guest/GuestHomeController';
import { PostLoginHandler } from '@/features/auth/PostLoginHandler';

interface HomePageProps {
  params: { locale: string };
}

/**
 * 홈 (`/`) — 게스트/회원 공용 셸 (FR-101).
 * RSC 는 정적 셸만 렌더하고(SSG 가능 — FR-110), 게스트 로직은 클라이언트에서 복원한다.
 * 빌드 타임 API 호출 없음.
 */
export default function HomePage({ params: { locale } }: HomePageProps) {
  setRequestLocale(locale);

  return (
    <>
      <Suspense fallback={null}>
        <PostLoginHandler />
      </Suspense>
      <GuestHomeController />
    </>
  );
}
