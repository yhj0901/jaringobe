'use client';

import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { fetchMe } from '@/features/auth/useSession';
import { resolvePostLoginAction } from '@/features/auth/postLogin';
import { importGuestPlan } from '@/features/budget/importGuestPlan';
import { useGuestStore } from '@/features/guest/store';
import { KNOWN_NOTICE_CODES } from '@/shared/config/constants';
import { useRouter, usePathname } from '@/i18n/routing';

/**
 * 로그인 복귀 처리 (?login=success[&notice=]) — ui-design 5장 분기 로직.
 * 홈(`/`)에 마운트되어 1회 실행된다.
 */
export function PostLoginHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const t = useTranslations();
  const ranRef = useRef(false);

  const [noticeCode, setNoticeCode] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const login = searchParams.get('login');
  const notice = searchParams.get('notice');

  useEffect(() => {
    if (login !== 'success' || ranRef.current) return;
    ranRef.current = true;

    // FR-004: 동일 이메일 타 provider 안내 — 로그인은 정상 진행, 배너만 표시
    if (notice !== null && (KNOWN_NOTICE_CODES as readonly string[]).includes(notice)) {
      setNoticeCode(notice);
    }

    const run = async () => {
      await useGuestStore.persist.rehydrate();
      const me = await fetchMe();
      if (!me.ok) {
        setFailed(true);
        return;
      }

      const guestPlan = useGuestStore.getState().plan;
      const action = resolvePostLoginAction(me.data, guestPlan !== undefined);

      if (action === 'stay') {
        router.replace(pathname);
        return;
      }
      if (action === 'go-onboarding') {
        router.push('/onboarding');
        return;
      }

      // FR-108: 게스트 예산안 이전
      if (guestPlan === undefined) return;
      const result = await importGuestPlan(guestPlan);
      if (result === 'created') {
        useGuestStore.getState().clearGuestData();
        router.push('/onboarding?imported=1');
      } else if (result === 'already-exists') {
        // 기존 활성 예산안 보유 — 로컬 게스트 데이터 삭제만 (api-spec 2-1)
        useGuestStore.getState().clearGuestData();
        router.replace(pathname);
      } else if (result === 'invalid') {
        // 변조 의심 — 게스트 값 폐기 후 일반 온보딩
        useGuestStore.getState().clearGuestData();
        router.push('/onboarding');
      } else {
        setFailed(true);
      }
    };
    void run();
  }, [login, notice, router, pathname]);

  if (noticeCode === null && !failed) return null;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-3">
      {noticeCode !== null ? (
        <p role="status" className="mb-2 rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-800">
          {t(`auth.notice.${noticeCode}`)}
        </p>
      ) : null}
      {failed ? (
        <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
          {t('common.error.fallback')}
        </p>
      ) : null}
    </div>
  );
}
