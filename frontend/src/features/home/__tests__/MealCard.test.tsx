import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { MealCard } from '@/features/home/MealCard';
import { renderWithIntl } from '@/test/renderWithIntl';
import type { MealItem } from '@/features/home/types';

const BASE: MealItem = {
  slot: 'breakfast',
  name: '계란볶음밥',
  isSample: false,
  mealId: 'm1',
  ingredients: ['계란', '밥'],
  estCost: { amount: '3500.00', currency: 'KRW' },
  completedAt: null,
};

describe('MealCard 완료 버튼 (FR-501/503)', () => {
  it('행 본문 클릭 → onRecipeClick 호출', () => {
    const onRecipeClick = vi.fn();
    renderWithIntl(<MealCard meal={BASE} onRecipeClick={onRecipeClick} />);
    fireEvent.click(screen.getByRole('button', { name: '계란볶음밥 레시피 보기' }));
    expect(onRecipeClick).toHaveBeenCalledTimes(1);
  });

  it('member 미완료: 파란 CTA "완료" → onToggleComplete 호출', () => {
    const onToggleComplete = vi.fn();
    renderWithIntl(<MealCard meal={BASE} onToggleComplete={onToggleComplete} />);
    const btn = screen.getByRole('button', { name: '계란볶음밥 식사 완료 체크' });
    expect(btn).toHaveAttribute('aria-pressed', 'false');
    expect(btn).toHaveTextContent('완료');
    fireEvent.click(btn);
    expect(onToggleComplete).toHaveBeenCalledTimes(1);
  });

  it('member 완료: 배지+체크 "완료됨" (재터치 해제) — aria-pressed=true', () => {
    const onToggleComplete = vi.fn();
    renderWithIntl(
      <MealCard
        meal={{ ...BASE, completedAt: '2026-07-08T10:00:00Z' }}
        onToggleComplete={onToggleComplete}
      />,
    );
    const btn = screen.getByRole('button', { name: '계란볶음밥 식사 완료 해제' });
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(btn).toHaveTextContent('완료됨');
    fireEvent.click(btn);
    expect(onToggleComplete).toHaveBeenCalledTimes(1);
  });

  it('completePending 이면 완료 버튼 비활성 (연타 방지)', () => {
    renderWithIntl(<MealCard meal={BASE} onToggleComplete={vi.fn()} completePending />);
    expect(screen.getByRole('button', { name: '계란볶음밥 식사 완료 체크' })).toBeDisabled();
  });

  it('게스트(onToggleComplete 미제공): 완료 버튼을 렌더하지 않는다', () => {
    renderWithIntl(<MealCard meal={{ ...BASE, isSample: true }} onRecipeClick={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /완료/ })).not.toBeInTheDocument();
    // 샘플 배지는 유지
    expect(screen.getByText('예시')).toBeInTheDocument();
  });
});
