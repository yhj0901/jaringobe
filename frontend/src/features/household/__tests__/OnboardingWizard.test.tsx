import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { OnboardingWizard } from '@/features/household/OnboardingWizard';
import { saveOnboardingPrefill, readOnboardingPrefill } from '@/features/household/prefill';
import { renderWithIntl } from '@/test/renderWithIntl';
import type { ApiResult } from '@/shared/api/client';

const routerMock = { push: vi.fn(), replace: vi.fn() };

vi.mock('@/i18n/routing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/i18n/routing')>();
  return {
    ...actual,
    useRouter: () => routerMock,
    usePathname: () => '/onboarding',
  };
});

vi.mock('@/features/household/api', () => ({
  putHouseholdMembers: vi.fn(),
  putBudgetPlan: vi.fn(),
}));
vi.mock('@/features/mealplan/api', () => ({
  createMealPlan: vi.fn(),
}));

const { putHouseholdMembers, putBudgetPlan } = await import('@/features/household/api');
const { createMealPlan } = await import('@/features/mealplan/api');

const householdMock = vi.mocked(putHouseholdMembers);
const budgetMock = vi.mocked(putBudgetPlan);
const mealplanMock = vi.mocked(createMealPlan);

function ok<T>(data: T, status = 200): ApiResult<T> {
  return { ok: true, status, data };
}

function err(status: number, code: string): ApiResult<never> {
  return { ok: false, status, code, i18nKey: 'common.error.fallback' };
}

function mockAllSuccess() {
  householdMock.mockResolvedValue(ok({ members: [], size: 2 }));
  budgetMock.mockResolvedValue(
    ok({
      id: 'b1',
      householdSize: 2,
      budget: { amount: '260000', currency: 'KRW' },
      mealDirection: 'health',
      source: 'onboarding',
      createdAt: '2026-07-09T00:00:00Z',
    }, 201),
  );
  mealplanMock.mockResolvedValue(
    ok(
      {
        id: 'plan-1',
        status: 'ready',
        region: 'KR',
        currency: 'KRW',
        periodStart: '2026-07-09',
        periodEnd: '2026-07-15',
        budgetSummary: {
          budget: { amount: '260000', currency: 'KRW' },
          plannedCost: { amount: '200000', currency: 'KRW' },
          remaining: { amount: '60000', currency: 'KRW' },
          withinBudget: true,
        },
        meals: [],
        notes: [],
      },
      201,
    ),
  );
}

function goToStep2() {
  fireEvent.click(screen.getByRole('button', { name: '다음' }));
}

function goToStep3() {
  goToStep2();
  fireEvent.click(screen.getByRole('button', { name: '다음' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
});

describe('OnboardingWizard STEP1 — 가구 구성원 (FR-311)', () => {
  it('기본 2인 프리셋 → 프리셋 버튼으로 4인 전환', () => {
    renderWithIntl(<OnboardingWizard />);

    expect(screen.getByText('STEP 1 / 3')).toBeInTheDocument();
    expect(screen.getByText('2인 가구')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2인' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: '4인' }));
    expect(screen.getByText('4인 가구')).toBeInTheDocument();
    // 4인 프리셋: 성인 남/여 + 어린이 2
    expect(screen.getAllByText('어린이')).toHaveLength(2);
  });

  it('구성원 추가/삭제 — 유형별 추가, 1명 남으면 삭제 버튼 없음', () => {
    renderWithIntl(<OnboardingWizard />);

    fireEvent.click(screen.getByRole('button', { name: '+ 유아' }));
    expect(screen.getByText('3인 가구')).toBeInTheDocument();
    expect(screen.getByText('유아')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '유아 삭제' }));
    expect(screen.getByText('2인 가구')).toBeInTheDocument();

    // 1인 프리셋 → 마지막 1명은 삭제 불가
    fireEvent.click(screen.getByRole('button', { name: '1인' }));
    expect(screen.queryByRole('button', { name: '성인 남성 삭제' })).not.toBeInTheDocument();
  });

  it('나이 스테퍼 — 기본 나이에서 증감, 유형 범위 경계에서 비활성', () => {
    renderWithIntl(<OnboardingWizard />);
    fireEvent.click(screen.getByRole('button', { name: '+ 유아' }));

    expect(screen.getByText('4세')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '유아 나이 늘리기' }));
    fireEvent.click(screen.getByRole('button', { name: '유아 나이 늘리기' }));
    expect(screen.getByText('6세')).toBeInTheDocument();
    // 유아 최대 6세 → 증가 비활성
    expect(screen.getByRole('button', { name: '유아 나이 늘리기' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '유아 나이 줄이기' }));
    expect(screen.getByText('5세')).toBeInTheDocument();
  });
});

describe('OnboardingWizard STEP2 — 예산 슬라이더·락 (FR-312)', () => {
  it('기본값 = 권장(인원×13만) + 슬라이더 범위/칩/최소 기준 문구', () => {
    renderWithIntl(<OnboardingWizard />);
    goToStep2();

    expect(screen.getByText('STEP 2 / 3')).toBeInTheDocument();
    expect(screen.getByText('₩260,000')).toBeInTheDocument();
    expect(screen.getByText(/1인 ₩130,000/)).toBeInTheDocument();
    expect(screen.getByText(/권장 ₩260,000/)).toBeInTheDocument();

    const slider = screen.getByRole('slider', { name: '월 예산' });
    expect(slider).toHaveAttribute('min', '160000');
    expect(slider).toHaveAttribute('max', '440000');
    expect(slider).toHaveAttribute('step', '10000');
  });

  it('수준 피드백 3단계 — 알뜰(≤권장)/적정(≤권장×1.3)/여유', () => {
    renderWithIntl(<OnboardingWizard />);
    goToStep2();

    expect(screen.getByText('알뜰한 예산이에요')).toBeInTheDocument();

    const slider = screen.getByRole('slider', { name: '월 예산' });
    fireEvent.change(slider, { target: { value: '300000' } });
    expect(screen.getByText('적정한 예산이에요')).toBeInTheDocument();

    fireEvent.change(slider, { target: { value: '440000' } });
    expect(screen.getByText('여유로운 예산이에요')).toBeInTheDocument();
  });

  it('예산 락 토글 — 기본 켜짐, 클릭으로 해제', () => {
    renderWithIntl(<OnboardingWizard />);
    goToStep2();

    const lockToggle = screen.getByRole('switch', { name: '예산 락' });
    expect(lockToggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText('켜짐 · 초과 지출 자동 차단')).toBeInTheDocument();

    fireEvent.click(lockToggle);
    expect(lockToggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('꺼짐 · 알림만 받아요')).toBeInTheDocument();
  });

  it('[이전] → STEP1 복귀, 인원 변경 후 재진입 시 예산 클램프', () => {
    renderWithIntl(<OnboardingWizard />);
    goToStep2();
    fireEvent.change(screen.getByRole('slider', { name: '월 예산' }), {
      target: { value: '440000' },
    });

    fireEvent.click(screen.getByRole('button', { name: '이전' }));
    expect(screen.getByText('STEP 1 / 3')).toBeInTheDocument();

    // 1인으로 줄이면 최대 22만 → 재진입 시 클램프
    fireEvent.click(screen.getByRole('button', { name: '1인' }));
    goToStep2();
    expect(screen.getByRole('slider', { name: '월 예산' })).toHaveValue('220000');
  });
});

describe('OnboardingWizard STEP3 — 선호·완료 (FR-313/314)', () => {
  it('음식 복수 선택 + 방향 단일 선택 → API 순서 호출(household→budget→mealplan) → 홈', async () => {
    mockAllSuccess();
    renderWithIntl(<OnboardingWizard />);
    goToStep3();

    expect(screen.getByText('STEP 3 / 3')).toBeInTheDocument();

    // 복수 선택
    fireEvent.click(screen.getByRole('button', { name: '한식' }));
    fireEvent.click(screen.getByRole('button', { name: '일식' }));
    expect(screen.getByRole('button', { name: '한식' })).toHaveAttribute('aria-pressed', 'true');
    // 재클릭 시 해제
    fireEvent.click(screen.getByRole('button', { name: '일식' }));
    fireEvent.click(screen.getByRole('button', { name: '일식' }));

    // 방향 단일 선택 (기본 health → kids)
    expect(screen.getByRole('radio', { name: /건강·영양 위주/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    fireEvent.click(screen.getByRole('radio', { name: /아이 입맛 위주/ }));
    expect(screen.getByRole('radio', { name: /아이 입맛 위주/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('radio', { name: /건강·영양 위주/ })).toHaveAttribute(
      'aria-checked',
      'false',
    );

    fireEvent.click(screen.getByRole('button', { name: '이 조건으로 식단 짜기' }));

    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));

    // FR-314: household → budget → mealplan 순서
    expect(householdMock).toHaveBeenCalledWith([
      { memberType: 'adult_m', age: 35 },
      { memberType: 'adult_f', age: 33 },
    ]);
    expect(budgetMock).toHaveBeenCalledWith({
      householdSize: 2,
      budget: { amount: '260000', currency: 'KRW' },
      mealDirection: 'kids',
      locked: true,
      cuisines: ['korean', 'japanese'],
    });
    // 선호 음식은 로캘 라벨로 preferences 전달
    expect(mealplanMock).toHaveBeenCalledWith({
      days: 7,
      mealsPerDay: 3,
      allergies: [],
      preferences: ['한식', '일식'],
    });

    const householdOrder = householdMock.mock.invocationCallOrder[0] ?? 0;
    const budgetOrder = budgetMock.mock.invocationCallOrder[0] ?? 0;
    const mealplanOrder = mealplanMock.mock.invocationCallOrder[0] ?? 0;
    expect(householdOrder).toBeLessThan(budgetOrder);
    expect(budgetOrder).toBeLessThan(mealplanOrder);
  });

  it('생성 중에는 GenerationLoading 오버레이 + CTA 비활성', async () => {
    householdMock.mockResolvedValue(ok({ members: [], size: 2 }));
    budgetMock.mockResolvedValue(ok({
      id: 'b1',
      householdSize: 2,
      budget: { amount: '260000', currency: 'KRW' },
      mealDirection: 'health',
      source: 'onboarding',
      createdAt: '2026-07-09T00:00:00Z',
    }));
    let resolveCreate: (value: ApiResult<never>) => void = () => undefined;
    mealplanMock.mockImplementation(
      () => new Promise((resolve) => (resolveCreate = resolve as typeof resolveCreate)),
    );

    renderWithIntl(<OnboardingWizard />);
    goToStep3();
    fireEvent.click(screen.getByRole('button', { name: '이 조건으로 식단 짜기' }));

    expect(await screen.findByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '이 조건으로 식단 짜기' })).toBeDisabled();

    resolveCreate(err(500, 'UNKNOWN'));
    await waitFor(() =>
      expect(screen.queryByText('예산에 맞는 식단을 만들고 있어요')).not.toBeInTheDocument(),
    );
  });

  it('단계별 실패 → 에러 배너 + 재시도는 실패 지점부터 재개 (FR-314)', async () => {
    renderWithIntl(<OnboardingWizard />);
    goToStep3();

    // 1) household 실패
    householdMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    fireEvent.click(screen.getByRole('button', { name: '이 조건으로 식단 짜기' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('가구 구성 저장에 실패했어요');

    // 2) 재시도: household 성공, budget 실패
    householdMock.mockResolvedValueOnce(ok({ members: [], size: 2 }));
    budgetMock.mockResolvedValueOnce(err(500, 'UNKNOWN'));
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('예산 저장에 실패했어요');
    expect(householdMock).toHaveBeenCalledTimes(2);

    // 3) 재시도: budget 성공, mealplan 429 → 대기 안내 (household 재호출 없음)
    budgetMock.mockResolvedValueOnce(ok({
      id: 'b1',
      householdSize: 2,
      budget: { amount: '260000', currency: 'KRW' },
      mealDirection: 'health',
      source: 'onboarding',
      createdAt: '2026-07-09T00:00:00Z',
    }));
    mealplanMock.mockResolvedValueOnce(err(429, 'RATE_LIMITED'));
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/1분 후 다시 시도해 주세요/);
    expect(householdMock).toHaveBeenCalledTimes(2);
    expect(budgetMock).toHaveBeenCalledTimes(2);

    // 4) 재시도: mealplan 성공 → 홈 (budget 재호출 없음)
    mockAllSuccess();
    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));
    expect(budgetMock).toHaveBeenCalledTimes(2);
    expect(mealplanMock).toHaveBeenCalledTimes(2);
  });
});

describe('OnboardingWizard 프리필·이전 확인 화면 (FR-108/315)', () => {
  it('imported=1 → 확인 화면 → [설정 이어서 하기] → STEP1', () => {
    renderWithIntl(<OnboardingWizard imported />);

    expect(screen.getByText('예산안을 계정으로 옮겼어요!')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '설정 이어서 하기' }));
    expect(screen.getByText('STEP 1 / 3')).toBeInTheDocument();
  });

  it('세션 프리필 → STEP1 인원·STEP2 예산·STEP3 방향 프리필 (스킵 아님)', async () => {
    saveOnboardingPrefill({
      householdSize: 4,
      amount: '700000',
      currency: 'KRW',
      mealDirection: 'hearty',
    });
    renderWithIntl(<OnboardingWizard />);

    // STEP1: 이전 인원 4인 프리셋
    await screen.findByText('4인 가구');

    goToStep2();
    // STEP2: 이전 금액 프리필 (4인 범위 내)
    expect(screen.getByText('₩700,000')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    // STEP3: 이전 방향 프리필
    expect(screen.getByRole('radio', { name: /든든·푸짐 위주/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('완료 성공 시 프리필 세션을 정리한다', async () => {
    saveOnboardingPrefill({
      householdSize: 2,
      amount: '300000',
      currency: 'KRW',
      mealDirection: 'health',
    });
    mockAllSuccess();
    renderWithIntl(<OnboardingWizard />);
    await screen.findByText('2인 가구');

    goToStep3();
    fireEvent.click(screen.getByRole('button', { name: '이 조건으로 식단 짜기' }));
    await waitFor(() => expect(routerMock.replace).toHaveBeenCalledWith('/'));
    expect(readOnboardingPrefill()).toBeNull();
  });
});

describe('OnboardingWizard guest 모드 — 게스트 체험 플로우 (서버 호출 없음)', () => {
  it('3스텝 완료 → onComplete 로 결과 반환, API·라우팅·생성 로딩 없음', () => {
    const onComplete = vi.fn();
    renderWithIntl(<OnboardingWizard mode="guest" onComplete={onComplete} />);

    // 오버레이 다이얼로그 + 동일한 STEP 문구
    expect(screen.getByRole('dialog', { name: '내 예산안 만들기' })).toBeInTheDocument();
    expect(screen.getByText('STEP 1 / 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '3인' }));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.change(screen.getByRole('slider', { name: '월 예산' }), {
      target: { value: '500000' },
    });
    fireEvent.click(screen.getByRole('switch', { name: '예산 락' }));
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    fireEvent.click(screen.getByRole('button', { name: '한식' }));
    fireEvent.click(screen.getByRole('radio', { name: /다이어트 위주/ }));
    fireEvent.click(screen.getByRole('button', { name: '이 조건으로 식단 짜기' }));

    expect(onComplete).toHaveBeenCalledWith({
      members: [
        { memberType: 'adult_m', age: 35 },
        { memberType: 'adult_f', age: 33 },
        { memberType: 'child', age: 9 },
      ],
      householdSize: 3,
      amount: '500000',
      currency: 'KRW',
      locked: false,
      cuisines: ['korean'],
      mealDirection: 'diet',
    });

    // 서버 호출·라우팅·생성 로딩 일절 없음
    expect(householdMock).not.toHaveBeenCalled();
    expect(budgetMock).not.toHaveBeenCalled();
    expect(mealplanMock).not.toHaveBeenCalled();
    expect(routerMock.replace).not.toHaveBeenCalled();
    expect(screen.queryByText('예산에 맞는 식단을 만들고 있어요')).not.toBeInTheDocument();
  });

  it('닫기 버튼 → onClose (onClose 없으면 버튼 미노출)', () => {
    const onClose = vi.fn();
    const { unmount } = renderWithIntl(
      <OnboardingWizard mode="guest" onComplete={vi.fn()} onClose={onClose} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    unmount();

    renderWithIntl(<OnboardingWizard mode="guest" onComplete={vi.fn()} />);
    expect(screen.queryByRole('button', { name: '닫기' })).not.toBeInTheDocument();
  });

  it('guest 모드는 온보딩 세션 프리필을 읽지 않는다', () => {
    saveOnboardingPrefill({
      householdSize: 4,
      amount: '700000',
      currency: 'KRW',
      mealDirection: 'hearty',
    });
    renderWithIntl(<OnboardingWizard mode="guest" onComplete={vi.fn()} />);
    // 프리필 무시 — 기본 2인
    expect(screen.getByText('2인 가구')).toBeInTheDocument();
  });
});

describe('OnboardingWizard 확장 프리필 — 게스트 위저드 결과 복원 (FR-315)', () => {
  it('members/cuisines/locked 확장분까지 3스텝 전부 프리필한다', async () => {
    saveOnboardingPrefill({
      householdSize: 2,
      amount: '300000',
      currency: 'KRW',
      mealDirection: 'diet',
      members: [
        { memberType: 'adult_f', age: 40 },
        { memberType: 'teen', age: 14 },
      ],
      cuisines: ['japanese'],
      locked: false,
    });
    renderWithIntl(<OnboardingWizard />);

    // STEP1: 구성원 유형·나이 그대로 복원 (프리셋 아님)
    await screen.findByText('성인 여성');
    expect(screen.getByText('청소년')).toBeInTheDocument();
    expect(screen.getByText('40세')).toBeInTheDocument();
    expect(screen.getByText('14세')).toBeInTheDocument();

    goToStep2();
    // STEP2: 금액 + 락 해제 상태 복원
    expect(screen.getByRole('slider', { name: '월 예산' })).toHaveValue('300000');
    expect(screen.getByRole('switch', { name: '예산 락' })).toHaveAttribute(
      'aria-checked',
      'false',
    );

    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    // STEP3: 음식·방향 복원
    expect(screen.getByRole('button', { name: '일식' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('radio', { name: /다이어트 위주/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });
});

describe('OnboardingWizard 로캘 통화 (글로벌)', () => {
  it('en 로캘 → USD 기준 슬라이더($60/$100/$170 × 인원)', () => {
    renderWithIntl(<OnboardingWizard />, 'en');
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    expect(screen.getByText('$200.00')).toBeInTheDocument();
    const slider = screen.getByRole('slider', { name: 'Monthly budget' });
    expect(slider).toHaveAttribute('min', '120');
    expect(slider).toHaveAttribute('max', '340');
    expect(slider).toHaveAttribute('step', '10');
  });
});
