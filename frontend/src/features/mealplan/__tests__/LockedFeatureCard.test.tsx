import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { LockedFeatureCard } from '@/features/mealplan/LockedFeatureCard';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('LockedFeatureCard (FR-208)', () => {
  it('냉장고 잠금 카드 — 제목/배지/설명', () => {
    renderWithIntl(<LockedFeatureCard feature="fridge" />);
    expect(screen.getByText('가상 냉장고')).toBeInTheDocument();
    expect(screen.getByText('준비 중')).toBeInTheDocument();
    expect(screen.getByText(/자동으로 등록되는 가상 냉장고/)).toBeInTheDocument();
  });

  it('자동주문 잠금 카드 — 제목/배지/설명', () => {
    renderWithIntl(<LockedFeatureCard feature="order" />);
    expect(screen.getByText('식재료 자동주문')).toBeInTheDocument();
    expect(screen.getByText('준비 중')).toBeInTheDocument();
  });

  it('en 로캘 렌더', () => {
    renderWithIntl(<LockedFeatureCard feature="fridge" />, 'en');
    expect(screen.getByText('Virtual fridge')).toBeInTheDocument();
    expect(screen.getByText('Coming soon')).toBeInTheDocument();
  });
});
