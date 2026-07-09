import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { EditOverlay } from '@/features/settings/EditOverlay';
import { renderWithIntl } from '@/test/renderWithIntl';

const BASE = {
  currency: 'KRW' as const,
  initialMembers: null,
  initialBudget: null,
  initialLocked: true,
  initialCuisines: [],
  initialDirection: 'health' as const,
  saving: false,
  saveError: false,
};

describe('EditOverlay 초기값 폴백 (FR-402)', () => {
  it('household — 구성원 없음(404) → 기본 2인 프리셋으로 시작', () => {
    const onSave = vi.fn();
    renderWithIntl(
      <EditOverlay {...BASE} section="household" onCancel={vi.fn()} onSave={onSave} />,
    );

    expect(screen.getByText('성인 남성')).toBeInTheDocument();
    expect(screen.getByText('성인 여성')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith({
      section: 'household',
      members: [
        { memberType: 'adult_m', age: 35 },
        { memberType: 'adult_f', age: 33 },
      ],
    });
  });

  it('household — 프리셋·나이 조절 결과를 저장 페이로드로 반환', () => {
    const onSave = vi.fn();
    renderWithIntl(
      <EditOverlay {...BASE} section="household" onCancel={vi.fn()} onSave={onSave} />,
    );

    fireEvent.click(screen.getByRole('button', { name: '1인' }));
    fireEvent.click(screen.getByRole('button', { name: '성인 남성 나이 늘리기' }));
    fireEvent.click(screen.getByRole('button', { name: '+ 유아' }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(onSave).toHaveBeenCalledWith({
      section: 'household',
      members: [
        { memberType: 'adult_m', age: 36 },
        { memberType: 'toddler', age: 4 },
      ],
    });
  });

  it('budget — 예산 요약 없음 → 인원 기반 권장값으로 시작 (2인 ₩260,000)', () => {
    const onSave = vi.fn();
    renderWithIntl(<EditOverlay {...BASE} section="budget" onCancel={vi.fn()} onSave={onSave} />);

    expect(screen.getByText('₩260,000')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith({ section: 'budget', amount: '260000', locked: true });
  });

  it('budget — 범위 밖 초기 금액은 슬라이더 범위로 클램프', () => {
    const onSave = vi.fn();
    renderWithIntl(
      <EditOverlay
        {...BASE}
        section="budget"
        initialBudget={{ amount: '700000.00', currency: 'KRW' }}
        onCancel={vi.fn()}
        onSave={onSave}
      />,
    );
    // 2인 최대 ₩440,000 으로 클램프 (대형 금액 + 슬라이더 max 라벨 2곳)
    expect(screen.getAllByText('₩440,000').length).toBeGreaterThanOrEqual(2);
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith({ section: 'budget', amount: '440000', locked: true });
  });

  it('saving 중 → 저장 오버레이 + PreferenceStep 버튼 비활성', () => {
    renderWithIntl(
      <EditOverlay {...BASE} section="preference" saving onCancel={vi.fn()} onSave={vi.fn()} />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('설정을 저장하고 있어요…');
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('saving 중 household 저장 클릭 → onSave 무시 (연타 방지)', () => {
    const onSave = vi.fn();
    renderWithIntl(
      <EditOverlay {...BASE} section="household" saving onCancel={vi.fn()} onSave={onSave} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).not.toHaveBeenCalled();
  });

  it('닫기(X) → onCancel', () => {
    const onCancel = vi.fn();
    renderWithIntl(
      <EditOverlay {...BASE} section="preference" onCancel={onCancel} onSave={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
