import type { Money } from '@/shared/api/types';

const LOCALE_TAG: Record<string, string> = {
  ko: 'ko-KR',
  en: 'en-US',
};

/**
 * 금액 로캘 포맷 문자열 생성 — Intl.NumberFormat 에 amount 문자열을 그대로 전달해
 * float 변환 없이 포맷한다 (ES2023 string 입력 지원, CLAUDE.md float 금지 원칙).
 */
export function formatMoney(money: Money, locale: string): string {
  const tag = LOCALE_TAG[locale] ?? locale;
  const formatter = new Intl.NumberFormat(tag, {
    style: 'currency',
    currency: money.currency,
  });
  // Intl.NumberFormat.format 은 문자열(Decimal string) 입력을 지원한다.
  return formatter.format(money.amount as unknown as number);
}

interface MoneyTextProps {
  money: Money;
  locale: string;
  className?: string;
}

/** 금액 표시 컴포넌트 — 통화 포함 낭독을 위해 단일 텍스트 노드로 렌더 */
export function MoneyText({ money, locale, className }: MoneyTextProps) {
  return <span className={className}>{formatMoney(money, locale)}</span>;
}
