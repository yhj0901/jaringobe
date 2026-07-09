import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { PostLoginHandler } from '@/features/auth/PostLoginHandler';
import { useGuestStore, type GuestPlan } from '@/features/guest/store';
import { GUEST_SCHEMA_VERSION, GUEST_STORAGE_KEY } from '@/shared/config/constants';
import { IntlWrapper } from '@/test/renderWithIntl';
import type { UserMeResponse } from '@/shared/api/types';

const searchParamsMock = { current: new URLSearchParams() };
const routerMock = { push: vi.fn(), replace: vi.fn() };

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParamsMock.current,
}));

vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/',
  };
});

vi.mock('@/features/auth/useSession', () => ({
  fetchMe: vi.fn(),
}));

vi.mock('@/features/budget/importGuestPlan', () => ({
  importGuestPlan: vi.fn(),
}));

const { fetchMe } = await import('@/features/auth/useSession');
const { importGuestPlan } = await import('@/features/budget/importGuestPlan');

const ME_BASE: UserMeResponse = {
  id: 'u1',
  nickname: '자린이',
  email: null,
  profileImageUrl: null,
  locale: 'ko',
  country: 'KR',
  currency: 'KRW',
  onboardingCompleted: false,
  hasBudgetPlan: false,
};

const GUEST_PLAN: GuestPlan = {
  householdSize: 2,
  amount: '500000',
  currency: 'KRW',
  mealDirection: 'health',
};

function seedGuestPlan() {
  window.localStorage.setItem(
    GUEST_STORAGE_KEY,
    JSON.stringify({
      state: { plan: GUEST_PLAN, promptHistory: {}, savedAt: new Date().toISOString() },
      version: GUEST_SCHEMA_VERSION,
    }),
  );
}

function mockMe(me: Partial<UserMeResponse>) {
  vi.mocked(fetchMe).mockResolvedValue({
    ok: true,
    status: 200,
    data: { ...ME_BASE, ...me },
  });
}

function renderHandler(query: string) {
  searchParamsMock.current = new URLSearchParams(query);
  return render(
    <IntlWrapper>
      <PostLoginHandler />
    </IntlWrapper>,
  );
}

describe('PostLoginHandler (ui-design 5장)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useGuestStore.setState({ plan: undefined, promptHistory: {}, savedAt: undefined });
  });

  it('login=success 가 아니면 아무것도 하지 않는다', () => {
    renderHandler('');
    expect(fetchMe).not.toHaveBeenCalled();
  });

  it('hasBudgetPlan=true → 쿼리만 제거하고 홈 유지', async () => {
    mockMe({ hasBudgetPlan: true });
    renderHandler('login=success');
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));
    expect(importGuestPlan).not.toHaveBeenCalled();
  });

  it('게스트 플랜 없음 → 홈 유지 (BudgetPlanGate 가 처리, FR-207)', async () => {
    mockMe({ hasBudgetPlan: false });
    renderHandler('login=success');
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalled());
    expect(routerMock.push).not.toHaveBeenCalledWith('/onboarding');
  });

  it('이전 성공(201) → 로컬 삭제 + 확인 화면 이동 (FR-108)', async () => {
    seedGuestPlan();
    mockMe({ hasBudgetPlan: false });
    vi.mocked(importGuestPlan).mockResolvedValue('created');
    renderHandler('login=success');

    await waitFor(() =>
      expect(routerMock.push).toHaveBeenCalledWith('/onboarding?imported=1'),
    );
    expect(importGuestPlan).toHaveBeenCalledWith(GUEST_PLAN);
    expect(useGuestStore.getState().plan).toBeUndefined();
  });

  it('409 기존 예산안 보유 → 로컬 삭제만 하고 홈 유지', async () => {
    seedGuestPlan();
    mockMe({ hasBudgetPlan: false });
    vi.mocked(importGuestPlan).mockResolvedValue('already-exists');
    renderHandler('login=success');

    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));
    expect(useGuestStore.getState().plan).toBeUndefined();
  });

  it('422 변조 의심 → 게스트 값 폐기 후 일반 온보딩', async () => {
    seedGuestPlan();
    mockMe({ hasBudgetPlan: false });
    vi.mocked(importGuestPlan).mockResolvedValue('invalid');
    renderHandler('login=success');

    await waitFor(() => expect(routerMock.replace).toHaveBeenCalled());
    expect(routerMock.push).not.toHaveBeenCalledWith('/onboarding');
    expect(useGuestStore.getState().plan).toBeUndefined();
  });

  it('이전 실패(네트워크 등) → 오류 배너 표시 + 로컬 데이터 유지', async () => {
    seedGuestPlan();
    mockMe({ hasBudgetPlan: false });
    vi.mocked(importGuestPlan).mockResolvedValue('error');
    renderHandler('login=success');

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(useGuestStore.getState().plan).toEqual(GUEST_PLAN);
  });

  it('users/me 실패 시 오류 배너를 표시한다', async () => {
    vi.mocked(fetchMe).mockResolvedValue({
      ok: false,
      status: 401,
      code: 'AUTH_REQUIRED',
      i18nKey: 'auth.error.AUTH_REQUIRED',
    });
    renderHandler('login=success');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('notice=AUTH_EMAIL_CONFLICT_NOTICE → 안내 배너를 표시한다 (FR-004)', async () => {
    mockMe({ hasBudgetPlan: true });
    renderHandler('login=success&notice=AUTH_EMAIL_CONFLICT_NOTICE');
    expect(await screen.findByRole('status')).toHaveTextContent(/다른 소셜 계정/);
  });

  it('알 수 없는 notice 코드는 무시한다', async () => {
    mockMe({ hasBudgetPlan: true });
    renderHandler('login=success&notice=SOMETHING_ELSE');
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalled());
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
