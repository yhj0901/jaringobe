import type { ReactNode } from 'react';

type BadgeTone = 'brand' | 'neutral' | 'warning';

const TONE_CLASS: Record<BadgeTone, string> = {
  brand: 'bg-brand-100 text-brand-700',
  neutral: 'bg-gray-100 text-gray-600',
  warning: 'bg-amber-100 text-amber-700',
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = 'neutral', children, className }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]} ${className ?? ''}`}
    >
      {children}
    </span>
  );
}
