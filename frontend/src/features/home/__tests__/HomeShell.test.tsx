import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { HomeShell } from '@/features/home/HomeShell';
import { getDefaultViewModel, getSampleViewModel } from '@/features/guest/sampleMatrix';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('HomeShell (FR-101)', () => {
  it('게스트 기본 모드: 체험 모드 배지 + 예시 라벨 + 샘플 위젯을 렌더한다', () => {
    renderWithIntl(<HomeShell viewModel={getDefaultViewModel('ko')} />);

    expect(screen.getByText('체험 모드')).toBeInTheDocument();
    expect(screen.getAllByText('예시').length).toBeGreaterThanOrEqual(3);
    // 예산 무드 (Money 로캘 포맷)
    expect(screen.getByText('남은 예산')).toBeInTheDocument();
    expect(screen.getByText('₩176,000')).toBeInTheDocument();
    // 식단 3카드 (아침/점심/저녁)
    expect(screen.getByText('아침')).toBeInTheDocument();
    expect(screen.getByText('점심')).toBeInTheDocument();
    expect(screen.getByText('저녁')).toBeInTheDocument();
    // 냉장고 임박 배너 (expiresInDays 1 항목 존재)
    expect(screen.getByText(/유통기한이 임박한 재료/)).toBeInTheDocument();
    // 자동주문 비활성
    expect(screen.getByText('대기 중')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '시작하기' })).not.toBeInTheDocument();
  });

  it('guest-planned 모드: 자동주문 활성 + 시작하기 CTA + 주문 추천을 렌더한다 (FR-106)', () => {
    const onStart = vi.fn();
    const vm = getSampleViewModel(
      'ko',
      { householdBand: '3-4', budgetBand: 'p3', direction: 'kids' },
      'guest-planned',
    );
    renderWithIntl(<HomeShell viewModel={vm} onAutoOrderStart={onStart} />);

    expect(screen.getByText('준비 완료')).toBeInTheDocument();
    expect(screen.getByText('이번 주 주문 추천')).toBeInTheDocument();
    const cta = screen.getByRole('button', { name: '시작하기' });
    fireEvent.click(cta);
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it('회원 모드에서는 체험 모드 배지를 숨긴다', () => {
    const vm = { ...getDefaultViewModel('ko'), mode: 'member' as const };
    renderWithIntl(<HomeShell viewModel={vm} />);
    expect(screen.queryByText('체험 모드')).not.toBeInTheDocument();
  });

  it('hideTrialBadge: 게스트 샘플 셸에서 체험 배지만 숨기고 예시 라벨은 유지한다 (ui-design 8장)', () => {
    renderWithIntl(<HomeShell viewModel={getDefaultViewModel('ko')} hideTrialBadge />);
    expect(screen.queryByText('체험 모드')).not.toBeInTheDocument();
    expect(screen.getAllByText('예시').length).toBeGreaterThanOrEqual(3);
  });

  it('전체 조리법 보기 클릭 시 가입 게이트 콜백을 호출한다 (FR-109)', () => {
    const onRecipeClick = vi.fn();
    renderWithIntl(<HomeShell viewModel={getDefaultViewModel('ko')} onRecipeClick={onRecipeClick} />);
    const buttons = screen.getAllByRole('button', { name: '전체 조리법 보기' });
    expect(buttons).toHaveLength(3);
    fireEvent.click(buttons[0] as HTMLElement);
    expect(onRecipeClick).toHaveBeenCalledTimes(1);
  });

  it('en 로캘에서 USD 금액과 영어 라벨을 렌더한다 (US-107)', () => {
    renderWithIntl(<HomeShell viewModel={getDefaultViewModel('en')} />, 'en');
    expect(screen.getByText('Trial mode')).toBeInTheDocument();
    expect(screen.getByText('$176.00')).toBeInTheDocument();
    expect(screen.getByText('Walmart')).toBeInTheDocument();
  });

  it('하단 탭바: 홈은 현재 탭, 잠긴 탭(식단/냉장고/장바구니) 클릭 시 게이트 콜백 (디자인 재현)', () => {
    const onLockedNavClick = vi.fn();
    renderWithIntl(
      <HomeShell viewModel={getDefaultViewModel('ko')} onLockedNavClick={onLockedNavClick} />,
    );

    const home = screen.getByRole('button', { name: '홈' });
    expect(home).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: '식단' }));
    fireEvent.click(screen.getByRole('button', { name: '냉장고' }));
    fireEvent.click(screen.getByRole('button', { name: '장바구니' }));
    expect(onLockedNavClick).toHaveBeenCalledTimes(3);
  });

  it('냉장고 항목을 임박 순으로 정렬해 표시한다', () => {
    renderWithIntl(<HomeShell viewModel={getDefaultViewModel('ko')} />);
    expect(screen.getByText('가상 냉장고')).toBeInTheDocument();
    const badges = screen.getAllByText(/일 남음/);
    expect(badges[0]).toHaveTextContent('1일 남음');
  });
});
