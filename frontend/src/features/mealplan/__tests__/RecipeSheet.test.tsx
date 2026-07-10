import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, within } from '@testing-library/react';
import { RecipeSheet } from '@/features/mealplan/RecipeSheet';
import { renderWithIntl } from '@/test/renderWithIntl';
import type { MealItem } from '@/features/home/types';

const REAL_MEAL: MealItem = {
  slot: 'dinner',
  name: '된장찌개',
  isSample: false,
  mealId: 'm9',
  recipeIngredients: [
    { name: '두부', quantity: '1', unit: '모' },
    { name: '애호박', quantity: '1', unit: '개' },
  ],
  steps: ['재료를 손질한다', '끓인다'],
  completedAt: null,
  timeMinutes: 15,
  difficulty: 'hard',
};

describe('RecipeSheet (FR-504)', () => {
  it('meal=null 이면 아무 것도 렌더하지 않는다', () => {
    const { container } = renderWithIntl(<RecipeSheet meal={null} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('실 레시피: 시간/난이도 실값 + householdSize 인분 + 재료 칩 + 실 steps 렌더', () => {
    renderWithIntl(<RecipeSheet meal={REAL_MEAL} householdSize={5} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog');

    expect(within(dialog).getByText('된장찌개')).toBeInTheDocument();
    expect(within(dialog).getByText('AI 추천 레시피')).toBeInTheDocument();
    expect(within(dialog).getByText('15분')).toBeInTheDocument();
    expect(within(dialog).getByText('어려움')).toBeInTheDocument();
    expect(within(dialog).getByText('5인분')).toBeInTheDocument();
    expect(within(dialog).getByText('두부 1모')).toBeInTheDocument();
    expect(within(dialog).getByText('애호박 1개')).toBeInTheDocument();
    expect(within(dialog).getByText('재료를 손질한다')).toBeInTheDocument();
    expect(within(dialog).getByText('끓인다')).toBeInTheDocument();
  });

  it('기본값 폴백: timeMinutes/difficulty/steps 부재 + householdSize 미지정 → 기본 라벨·2인분·기본 조리법', () => {
    const bare: MealItem = { slot: 'breakfast', name: '토스트', isSample: false };
    renderWithIntl(<RecipeSheet meal={bare} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog');

    expect(within(dialog).getByText('약 20분')).toBeInTheDocument();
    expect(within(dialog).getByText('쉬움')).toBeInTheDocument();
    expect(within(dialog).getByText('2인분')).toBeInTheDocument();
    // 재료 없음 → 재료 섹션 미표시
    expect(within(dialog).queryByText('재료')).not.toBeInTheDocument();
    // 기본 조리법 3단계
    expect(within(dialog).getByText(/재료를 깨끗이 씻고/)).toBeInTheDocument();
    expect(within(dialog).getByText(/그릇에 보기 좋게/)).toBeInTheDocument();
  });

  it('닫기 버튼 → onClose 호출', () => {
    const onClose = vi.fn();
    renderWithIntl(<RecipeSheet meal={REAL_MEAL} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('en 로캘 라벨 렌더', () => {
    renderWithIntl(<RecipeSheet meal={REAL_MEAL} householdSize={3} onClose={vi.fn()} />, 'en');
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('AI recipe')).toBeInTheDocument();
    expect(within(dialog).getByText('15 min')).toBeInTheDocument();
    expect(within(dialog).getByText('Hard')).toBeInTheDocument();
    expect(within(dialog).getByText('Serves 3')).toBeInTheDocument();
  });
});
