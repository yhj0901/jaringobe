import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { MoneyText, formatMoney } from '@/shared/ui/MoneyText';
import { renderWithIntl } from '@/test/renderWithIntl';

describe('formatMoney', () => {
  it('KRW 금액을 ko-KR 로캘로 포맷한다', () => {
    expect(formatMoney({ amount: '500000', currency: 'KRW' }, 'ko')).toBe('₩500,000');
  });

  it('소수 둘째 자리 Decimal 문자열을 정밀도 손실 없이 포맷한다', () => {
    expect(formatMoney({ amount: '700000.00', currency: 'KRW' }, 'ko')).toBe('₩700,000');
  });

  it('USD 금액을 en-US 로캘로 포맷한다', () => {
    expect(formatMoney({ amount: '300', currency: 'USD' }, 'en')).toBe('$300.00');
  });

  it('알 수 없는 로캘 문자열은 그대로 Intl 에 전달한다', () => {
    expect(formatMoney({ amount: '100', currency: 'USD' }, 'en-GB')).toBe('US$100.00');
  });
});

describe('MoneyText', () => {
  it('통화 포함 단일 텍스트 노드로 렌더한다', () => {
    renderWithIntl(<MoneyText money={{ amount: '50000', currency: 'KRW' }} locale="ko" />);
    expect(screen.getByText('₩50,000')).toBeInTheDocument();
  });
});
