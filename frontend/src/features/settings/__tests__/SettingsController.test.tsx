import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { SettingsController } from '@/features/settings/SettingsController';
import type { SettingsState } from '@/features/settings/useSettings';
import { renderWithIntl } from '@/test/renderWithIntl';

const state: { current: SettingsState } = { current: undefined as unknown as SettingsState };
const routerMock = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() };

vi.mock('@/features/settings/useSettings', () => ({
  useSettings: () => state.current,
}));
vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/settings',
  };
});

const USER = {
  id: 'u1',
  nickname: '자린이',
  email: 'me@example.com',
  profileImageUrl: null,
  locale: 'ko',
  country: 'KR',
  currency: 'KRW',
  onboardingCompleted: true,
  hasBudgetPlan: true,
};

const MEMBERS = [
  { memberType: 'adult_m' as const, age: 35 },
  { memberType: 'adult_f' as const, age: 33 },
];

function baseState(overrides: Partial<SettingsState> = {}): SettingsState {
  return {
    status: 'ready',
    user: USER,
    members: MEMBERS,
    // 2인 가구 슬라이더 범위(₩160,000~₩440,000) 내 금액 — 편집 초기값 클램프 검증 단순화
    budget: { amount: '420000.00', currency: 'KRW' },
    planId: 'plan-1',
    connections: { kurly: true, coupang: false, ssg: false, naver: false },
    storeIds: ['kurly', 'coupang', 'ssg', 'naver'],
    profile: { direction: 'health', cuisines: [], locked: true, known: false },
    saving: false,
    togglingStore: null,
    switchingRegion: false,
    generating: false,
    loggingOut: false,
    saveHousehold: vi.fn().mockResolvedValue(true),
    saveBudget: vi.fn().mockResolvedValue(true),
    savePreference: vi.fn().mockResolvedValue(true),
    toggleStore: vi.fn().mockResolvedValue(true),
    switchRegion: vi.fn().mockResolvedValue(true),
    regenerate: vi.fn().mockResolvedValue('ok'),
    logout: vi.fn().mockResolvedValue(true),
    reload: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  state.current = baseState();
});

describe('SettingsController 화면 구성 (FR-401/402/404)', () => {
  it('loading — 스켈레톤을 렌더한다', () => {
    state.current = baseState({ status: 'loading' });
    renderWithIntl(<SettingsController />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('unauthenticated — /login?next=/settings 로 이동한다', async () => {
    state.current = baseState({ status: 'unauthenticated' });
    renderWithIntl(<SettingsController />);
    await waitFor(() =>
      expect(routerMock.replace).toHaveBeenCalledWith('/login?next=/settings'),
    );
  });

  it('error — 오류 문구 + 다시 불러오기', () => {
    state.current = baseState({ status: 'error', user: null, connections: null });
    renderWithIntl(<SettingsController />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '다시 불러오기' }));
    expect(state.current.reload).toHaveBeenCalledTimes(1);
  });

  it('ready — 계정 카드(프로필·로그인됨)와 3행 요약·스토어 리스트를 렌더한다', () => {
    renderWithIntl(<SettingsController />);

    // 계정 카드 (FR-401)
    expect(screen.getByText('자린이')).toBeInTheDocument();
    expect(screen.getByText('me@example.com')).toBeInTheDocument();
    expect(screen.getByText('로그인됨')).toBeInTheDocument();

    // 내 식생활 설정 3행 요약 (FR-402): N인 가구 / 미확정 선호 "설정됨" / 월 예산
    expect(screen.getByText('2인 가구')).toBeInTheDocument();
    expect(screen.getByText('설정됨 · 탭해서 변경')).toBeInTheDocument();
    expect(screen.getByText('월 ₩420,000')).toBeInTheDocument();

    // 스토어 리스트 (FR-404): 연동됨(컬리) + 연동하기(쿠팡 등)
    expect(screen.getByText('마켓컬리')).toBeInTheDocument();
    expect(screen.getByText('연동됨')).toBeInTheDocument();
    expect(screen.getByText(/연동 계정 · me@example.com/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '마켓컬리 연동 해제' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '쿠팡 연동하기' })).toBeInTheDocument();
  });

  it('이메일 미제공(null) → 대체 문구 표시', () => {
    state.current = baseState({ user: { ...USER, email: null } });
    renderWithIntl(<SettingsController />);
    expect(screen.getByText('이메일 미제공')).toBeInTheDocument();
  });

  it('가구·예산 미설정 → "아직 설정 전" 요약 (FR-402)', () => {
    state.current = baseState({
      members: null,
      budget: null,
      planId: null,
      user: { ...USER, hasBudgetPlan: false },
    });
    renderWithIntl(<SettingsController />);
    expect(screen.getAllByText('아직 설정 전이에요').length).toBe(2);
  });

  it('예산 요약 없음 + 예산안 보유 → "설정됨" 표기 (설계 재량)', () => {
    state.current = baseState({ budget: null, planId: null });
    renderWithIntl(<SettingsController />);
    // 선호 행 + 예산 행 모두 "설정됨"
    expect(screen.getAllByText('설정됨 · 탭해서 변경').length).toBe(2);
  });

  it('선호 확정(known) 후에는 방향·선호 라벨을 요약한다', () => {
    state.current = baseState({
      profile: { direction: 'kids', cuisines: ['korean', 'salad'], locked: true, known: true },
    });
    renderWithIntl(<SettingsController />);
    expect(screen.getByText('아이 입맛 · 한식 · 샐러드·채식')).toBeInTheDocument();
  });

  it('뒤로가기 → 홈 이동', () => {
    renderWithIntl(<SettingsController />);
    fireEvent.click(screen.getByRole('button', { name: '홈으로 돌아가기' }));
    expect(routerMock.push).toHaveBeenCalledWith('/');
  });
});

describe('식생활 단일 편집 → 재생성 확인 (FR-402/403)', () => {
  it('가구 행 → MemberStep 편집 → 저장 → 재생성 확인 → 수락 시 재생성 후 홈', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /가구 구성/ }));
    // 단일 편집 오버레이 (MemberStep 재사용 + 저장 라벨)
    expect(screen.getByRole('dialog', { name: '식생활 설정 편집' })).toBeInTheDocument();
    // 초기값 주입 — 현재 구성원 2명
    expect(screen.getByText('성인 남성')).toBeInTheDocument();
    expect(screen.getByText('성인 여성')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(state.current.saveHousehold).toHaveBeenCalledWith(MEMBERS),
    );

    // 저장 성공 → "식단을 다시 만들까요?" 확인 시트 (FR-403)
    expect(await screen.findByText('식단을 다시 만들까요?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '다시 만들기' }));
    await waitFor(() => expect(state.current.regenerate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));
  });

  it('재생성 거절 → 설정 잔류 (FR-403)', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /가구 구성/ }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('식단을 다시 만들까요?')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '나중에' }));
    expect(screen.queryByText('식단을 다시 만들까요?')).not.toBeInTheDocument();
    expect(state.current.regenerate).not.toHaveBeenCalled();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });

  it('예산 행 → BudgetStep 편집(취소/저장 라벨) → 저장 시 금액·락 전달', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /월 예산·예산 락/ }));
    // 초기값 주입 — 현재 예산 420,000
    expect(screen.getByText('₩420,000')).toBeInTheDocument();

    // 락 토글 → 꺼짐
    fireEvent.click(screen.getByRole('switch', { name: '예산 락' }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() =>
      expect(state.current.saveBudget).toHaveBeenCalledWith('420000', false),
    );
    expect(await screen.findByText('식단을 다시 만들까요?')).toBeInTheDocument();
  });

  it('선호 행 → PreferenceStep 편집 → 선호·방향 저장', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /선호 음식·식단 방향/ }));
    fireEvent.click(screen.getByRole('button', { name: /한식/ }));
    fireEvent.click(screen.getByRole('radio', { name: /아이 입맛 위주/ }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() =>
      expect(state.current.savePreference).toHaveBeenCalledWith(['korean'], 'kids'),
    );
  });

  it('저장 실패 → 오버레이 유지 + 오류 배너', async () => {
    state.current = baseState({ saveHousehold: vi.fn().mockResolvedValue(false) });
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /가구 구성/ }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      '저장에 실패했어요. 다시 시도해 주세요.',
    );
    expect(screen.getByRole('dialog', { name: '식생활 설정 편집' })).toBeInTheDocument();
    expect(screen.queryByText('식단을 다시 만들까요?')).not.toBeInTheDocument();
  });

  it('편집 취소(닫기) → 저장 없이 오버레이 닫힘', () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /월 예산·예산 락/ }));
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.queryByRole('dialog', { name: '식생활 설정 편집' })).not.toBeInTheDocument();
    expect(state.current.saveBudget).not.toHaveBeenCalled();
  });

  it('재생성 실패(429) → 대기 안내 배너 + 잔류, 닫기로 해제', async () => {
    state.current = baseState({ regenerate: vi.fn().mockResolvedValue('rate-limited') });
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /가구 구성/ }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    fireEvent.click(await screen.findByRole('button', { name: '다시 만들기' }));

    expect(
      await screen.findByText(/요청이 많아 잠시 쉬어가는 중이에요/),
    ).toBeInTheDocument();
    expect(routerMock.replace).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(screen.queryByText(/요청이 많아 잠시 쉬어가는 중이에요/)).not.toBeInTheDocument();
  });

  it('재생성 실패(일반) → 생성 실패 배너', async () => {
    state.current = baseState({ regenerate: vi.fn().mockResolvedValue('failed') });
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: /가구 구성/ }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    fireEvent.click(await screen.findByRole('button', { name: '다시 만들기' }));

    expect(await screen.findByText(/식단 생성에 실패했어요/)).toBeInTheDocument();
  });

  it('재생성 중 → GenerationLoading 노출 (FR-403 로딩 재사용)', () => {
    state.current = baseState({ generating: true });
    renderWithIntl(<SettingsController />);
    expect(screen.getByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
  });
});

describe('스토어 연동 토글 (FR-404)', () => {
  it('연동하기 → 1단계 안내 확인 시트 → 수락 시 PUT', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '쿠팡 연동하기' }));
    // 확인 시트 — "연동 표시만 저장" 안내 (i18n)
    expect(screen.getByText('쿠팡 연동하기')).toBeInTheDocument();
    expect(
      screen.getByText(/지금은 연동 표시만 저장되며, 실제 계정 연결과 자동 결제는 준비 중이에요/),
    ).toBeInTheDocument();

    const sheet = screen.getByRole('dialog');
    fireEvent.click(within(sheet).getByRole('button', { name: '연동하기' }));
    await waitFor(() =>
      expect(state.current.toggleStore).toHaveBeenCalledWith('coupang', true),
    );
  });

  it('해제 → 해제 확인 시트 → 수락 시 PUT(connected=false)', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '마켓컬리 연동 해제' }));
    expect(screen.getByText('마켓컬리 연동을 해제할까요?')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '해제하기' }));
    await waitFor(() =>
      expect(state.current.toggleStore).toHaveBeenCalledWith('kurly', false),
    );
  });

  it('확인 시트 취소 → PUT 미호출', () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '쿠팡 연동하기' }));
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(state.current.toggleStore).not.toHaveBeenCalled();
  });

  it('토글 실패 → 오류 배너', async () => {
    state.current = baseState({ toggleStore: vi.fn().mockResolvedValue(false) });
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '쿠팡 연동하기' }));
    const sheet = screen.getByRole('dialog');
    fireEvent.click(within(sheet).getByRole('button', { name: '연동하기' }));

    expect(await screen.findByText(/연동 상태 변경에 실패했어요/)).toBeInTheDocument();
  });
});

describe('지역·통화 전환 (FR-601/605)', () => {
  const US_STATE: Partial<SettingsState> = {
    user: { ...USER, country: 'US', currency: 'USD' },
    connections: { walmart: false, instacart: false },
    storeIds: ['walmart', 'instacart'],
  };

  it('KR 기본 → 글로벌 배지 없음 + 한국/글로벌 토글 노출', () => {
    renderWithIntl(<SettingsController />);
    expect(screen.getByRole('button', { name: '한국 ₩' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '글로벌 $' })).toBeInTheDocument();
    expect(screen.queryByText('글로벌')).not.toBeInTheDocument();
  });

  it('글로벌 $ 클릭 → 전환 확인 시트 → 수락 시 switchRegion(US)', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '글로벌 $' }));
    expect(screen.getByText('지역을 전환할까요?')).toBeInTheDocument();

    const sheet = screen.getByRole('dialog');
    fireEvent.click(within(sheet).getByRole('button', { name: '전환하기' }));
    await waitFor(() => expect(state.current.switchRegion).toHaveBeenCalledWith('US'));
  });

  it('전환 취소 → switchRegion 미호출', () => {
    renderWithIntl(<SettingsController />);
    fireEvent.click(screen.getByRole('button', { name: '글로벌 $' }));
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(state.current.switchRegion).not.toHaveBeenCalled();
  });

  it('US 지역 → 글로벌 배지 + US 스토어(월마트/인스타카트) 렌더', () => {
    state.current = baseState(US_STATE);
    renderWithIntl(<SettingsController />);
    expect(screen.getByText('글로벌')).toBeInTheDocument();
    expect(screen.getByText('월마트')).toBeInTheDocument();
    expect(screen.getByText('인스타카트')).toBeInTheDocument();
    expect(screen.queryByText('마켓컬리')).not.toBeInTheDocument();
  });

  it('전환 실패 → 오류 배너', async () => {
    state.current = baseState({ switchRegion: vi.fn().mockResolvedValue(false) });
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '글로벌 $' }));
    const sheet = screen.getByRole('dialog');
    fireEvent.click(within(sheet).getByRole('button', { name: '전환하기' }));
    expect(await screen.findByText(/지역 전환에 실패했어요/)).toBeInTheDocument();
  });
});

describe('로그아웃 (FR-401)', () => {
  it('로그아웃 → 확인 시트 → 수락 시 logout() 후 홈 이동', async () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    expect(screen.getByText('로그아웃할까요?')).toBeInTheDocument();

    const sheet = screen.getByRole('dialog');
    fireEvent.click(within(sheet).getByRole('button', { name: '로그아웃' }));
    await waitFor(() => expect(state.current.logout).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));
    expect(routerMock.refresh).toHaveBeenCalled();
  });

  it('로그아웃 확인 취소 → 호출 없음', () => {
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    fireEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(state.current.logout).not.toHaveBeenCalled();
  });

  it('로그아웃 실패 → 오류 배너 + 잔류', async () => {
    state.current = baseState({ logout: vi.fn().mockResolvedValue(false) });
    renderWithIntl(<SettingsController />);

    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }));
    const sheet = screen.getByRole('dialog');
    fireEvent.click(within(sheet).getByRole('button', { name: '로그아웃' }));

    expect(await screen.findByText(/로그아웃에 실패했어요/)).toBeInTheDocument();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });
});
