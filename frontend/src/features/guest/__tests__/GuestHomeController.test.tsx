import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { GuestHomeController } from '@/features/guest/GuestHomeController';
import { useGuestStore, type GuestPlan } from '@/features/guest/store';
import {
  GUEST_SCHEMA_VERSION,
  GUEST_STORAGE_KEY,
  PROMPT_DECLINED_SESSION_KEY,
  PROMPT_DWELL_MS,
} from '@/shared/config/constants';
import { IntlWrapper } from '@/test/renderWithIntl';

const routerMock = { push: vi.fn(), replace: vi.fn() };

vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/',
  };
});

const GUEST_PLAN: GuestPlan = {
  householdSize: 4,
  amount: '700000',
  currency: 'KRW',
  mealDirection: 'kids',
};

function seedPlan(plan: GuestPlan, autoOrderNotifiedAt?: string) {
  window.localStorage.setItem(
    GUEST_STORAGE_KEY,
    JSON.stringify({
      state: {
        plan,
        promptHistory: autoOrderNotifiedAt !== undefined ? { autoOrderNotifiedAt } : {},
        savedAt: new Date().toISOString(),
      },
      version: GUEST_SCHEMA_VERSION,
    }),
  );
}

async function renderController() {
  const utils = render(
    <IntlWrapper>
      <GuestHomeController />
    </IntlWrapper>,
  );
  // rehydrate 마이크로태스크 플러시
  await act(async () => {});
  return utils;
}

describe('GuestHomeController', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.sessionStorage.clear();
    useGuestStore.setState({ plan: undefined, promptHistory: {}, savedAt: undefined });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('기본 모드: 체험 모드 배지 + 비활성 자동주문을 렌더한다 (FR-101)', async () => {
    await renderController();
    expect(screen.getByText('체험 모드')).toBeInTheDocument();
    expect(screen.getByText('대기 중')).toBeInTheDocument();
    expect(screen.queryByText('예산안을 작성해 보시겠어요?')).not.toBeInTheDocument();
  });

  it('체류 10초 후 프롬프트 → 아니오 → 상시 CTA 배너 (FR-102/103)', async () => {
    vi.useFakeTimers();
    await renderController();

    await act(async () => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS + 500);
    });
    expect(screen.getByText('예산안을 작성해 보시겠어요?')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '아니오' }));
    expect(screen.queryByText('예산안을 작성해 보시겠어요?')).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem(PROMPT_DECLINED_SESSION_KEY)).toBe('1');
    expect(screen.getByRole('button', { name: '예산안 만들어보기' })).toBeInTheDocument();
  });

  it('CTA 배너 클릭으로 예산안 플로우를 다시 열 수 있다 (FR-103)', async () => {
    window.sessionStorage.setItem(PROMPT_DECLINED_SESSION_KEY, '1');
    await renderController();
    fireEvent.click(screen.getByRole('button', { name: '예산안 만들어보기' }));
    expect(screen.getByText('내 예산안 만들기')).toBeInTheDocument();
  });

  it('프롬프트 예 → 3스텝 완료 → 홈 갱신 + 자동주문 알림 1회 (FR-104/105/106)', async () => {
    vi.useFakeTimers();
    await renderController();

    await act(async () => {
      vi.advanceTimersByTime(PROMPT_DWELL_MS + 500);
    });
    fireEvent.click(screen.getByRole('button', { name: '예' }));
    expect(screen.getByText('내 예산안 만들기')).toBeInTheDocument();

    // 3스텝: 인원 4 → 70만원 → 아이 입맛
    fireEvent.click(screen.getByLabelText('인원 늘리기'));
    fireEvent.click(screen.getByLabelText('인원 늘리기'));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.click(screen.getByRole('radio', { name: '₩700,000' }));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.click(screen.getByRole('button', { name: '아이 입맛' }));

    // 적용 연출 후 홈 갱신
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getByText('준비 완료')).toBeInTheDocument();
    // kids 방향 샘플 식단으로 갱신됨
    expect(screen.getByText('치즈 달걀말이와 주먹밥')).toBeInTheDocument();

    // 자동주문 알림 1회 + promptHistory 기록
    expect(screen.getByText('자동주문을 시작해볼까요?')).toBeInTheDocument();
    expect(useGuestStore.getState().promptHistory.autoOrderNotifiedAt).toBeDefined();

    // 시작하기 → /login?next=/
    fireEvent.click(screen.getAllByRole('button', { name: '시작하기' })[0] as HTMLElement);
    expect(routerMock.push).toHaveBeenCalledWith('/login?next=/');
  });

  it('재방문: localStorage 예산안 복원 → planned 홈 (FR-107, US-106)', async () => {
    seedPlan(GUEST_PLAN, new Date().toISOString());
    await renderController();

    expect(screen.getByText('준비 완료')).toBeInTheDocument();
    expect(screen.getByText('체험 모드')).toBeInTheDocument();
    // 이미 알림을 본 사용자에게 재노출 없음
    expect(screen.queryByText('자동주문을 시작해볼까요?')).not.toBeInTheDocument();
  });

  it('알림 미노출 이력이면 복원 직후 자동주문 알림을 1회 표시한다 (FR-106)', async () => {
    seedPlan(GUEST_PLAN);
    await renderController();
    expect(screen.getByText('자동주문을 시작해볼까요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '나중에' }));
    expect(screen.queryByText('자동주문을 시작해볼까요?')).not.toBeInTheDocument();
  });

  it('예산안 있는 게스트의 전체 조리법 보기 → 가입 게이트 모달 → 로그인 이동 (FR-109)', async () => {
    seedPlan(GUEST_PLAN, new Date().toISOString());
    await renderController();
    fireEvent.click(screen.getAllByRole('button', { name: '전체 조리법 보기' })[0] as HTMLElement);
    expect(screen.getByText('저장하려면 로그인이 필요해요')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '로그인하기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/login?next=/');
  });

  it('자동주문 카드 활성 CTA 도 로그인으로 이동한다 (FR-106)', async () => {
    seedPlan(GUEST_PLAN, new Date().toISOString());
    await renderController();
    fireEvent.click(screen.getByRole('button', { name: '시작하기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/login?next=/');
  });

  it('예산안 없을 때 잠긴 탭 클릭 → 가입 게이트 대신 예산안 작성 플로우가 열린다', async () => {
    await renderController();
    const fridgeTab = screen.getByRole('button', { name: '냉장고' });
    fireEvent.click(fridgeTab);
    // BudgetDraftFlow 1단계(인원) 노출, 가입 게이트 문구는 없음
    expect(screen.getByText('몇 명이 함께 식사하나요?')).toBeInTheDocument();
    expect(screen.queryByText('저장하려면 로그인이 필요해요')).not.toBeInTheDocument();
  });

  it('예산안 있을 때 잠긴 탭 클릭 → 가입 게이트가 열린다', async () => {
    seedPlan(GUEST_PLAN, new Date().toISOString());
    await renderController();
    const fridgeTab = screen.getByRole('button', { name: '냉장고' });
    fireEvent.click(fridgeTab);
    expect(screen.getByText('저장하려면 로그인이 필요해요')).toBeInTheDocument();
  });
});
