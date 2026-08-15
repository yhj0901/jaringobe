import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { AutoOrderCard } from '@/features/home/AutoOrderCard';
import { renderWithIntl } from '@/test/renderWithIntl';

const inactive = {
  active: false,
  stores: [{ id: 'kurly', name: '마켓컬리' }],
};

const active = {
  active: true,
  stores: [{ id: 'kurly', name: '마켓컬리' }],
  recommendedItems: ['계란', '양파'],
  moreCount: 2,
};

describe('AutoOrderCard 게스트 기본 (카피 불변)', () => {
  it('비활성: 시작하기 버튼 없음, 게스트 설명', () => {
    renderWithIntl(<AutoOrderCard autoOrder={inactive} />);
    expect(screen.getByText('대기 중')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '시작하기' })).not.toBeInTheDocument();
    expect(screen.getByText(/예산안을 만들면/)).toBeInTheDocument();
  });

  it('활성: 시작하기 CTA + 추천 칩 (게스트 키)', () => {
    const onStart = vi.fn();
    renderWithIntl(<AutoOrderCard autoOrder={active} onStart={onStart} />);
    expect(screen.getByText('이번 주 주문 추천')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '시작하기' }));
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('+2')).not.toBeInTheDocument();
  });
});

describe('AutoOrderCard 회원 optional props', () => {
  it('비활성 + inactiveCtaLabel → 연동 CTA', () => {
    const onStart = vi.fn();
    renderWithIntl(
      <AutoOrderCard
        autoOrder={inactive}
        onStart={onStart}
        inactiveCtaLabel="스토어 연동하기"
        description="스토어를 연동하면 장보기 목록을 확정할 수 있어요."
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '스토어 연동하기' }));
    expect(onStart).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '시작하기' })).not.toBeInTheDocument();
  });

  it('활성 + ctaLabel/moreCountLabel → 회원 CTA + +K', () => {
    renderWithIntl(
      <AutoOrderCard
        autoOrder={active}
        ctaLabel="장바구니 보기"
        moreCountLabel="+2"
        recommendedLabel="이번 주 주문 추천"
      />,
    );
    expect(screen.getByRole('button', { name: '장바구니 보기' })).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
  });
});
