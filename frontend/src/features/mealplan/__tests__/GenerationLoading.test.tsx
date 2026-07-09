import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import { GenerationLoading } from '@/features/mealplan/GenerationLoading';
import { GENERATION_STEP_INTERVAL_MS } from '@/features/mealplan/constants';
import { renderWithIntl } from '@/test/renderWithIntl';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('GenerationLoading (FR-204)', () => {
  it('aria-busy 라이브 리전 + 스켈레톤을 렌더한다 (접근성)', () => {
    renderWithIntl(<GenerationLoading />);
    const region = screen.getByRole('status');
    expect(region).toHaveAttribute('aria-busy', 'true');
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('예산에 맞는 식단을 만들고 있어요')).toBeInTheDocument();
  });

  it('단계 문구를 인터벌마다 로테이션한다 (step1 → step2 → step3 → step1)', () => {
    renderWithIntl(<GenerationLoading />);
    expect(screen.getByText('예산과 가구 정보를 확인하고 있어요…')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(GENERATION_STEP_INTERVAL_MS));
    expect(screen.getByText('예산 안에서 재료를 고르고 있어요…')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(GENERATION_STEP_INTERVAL_MS));
    expect(screen.getByText('한 주 식단을 차곡차곡 담고 있어요…')).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(GENERATION_STEP_INTERVAL_MS));
    expect(screen.getByText('예산과 가구 정보를 확인하고 있어요…')).toBeInTheDocument();
  });
});
