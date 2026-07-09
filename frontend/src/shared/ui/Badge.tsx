import type { ReactNode } from 'react';

type BadgeTone = 'brand' | 'neutral' | 'warning';

/** 디자인 프로토타입 칩 톤 — 블루/뉴트럴/오렌지 */
const TONE_CLASS: Record<BadgeTone, string> = {
  brand: 'bg-brand-50 text-brand-600',
  neutral: 'bg-[#F0F2F6] text-ink-500',
  warning: 'bg-flame-50 text-flame-600',
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = 'neutral', children, className }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${TONE_CLASS[tone]} ${className ?? ''}`}
    >
      {children}
    </span>
  );
}
