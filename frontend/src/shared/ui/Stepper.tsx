'use client';

interface StepperProps {
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
  label: string;
  decrementLabel: string;
  incrementLabel: string;
}

/** 숫자 스테퍼 — 키보드 조작 가능 버튼 + 범위 클램프 (CWE-20 클라이언트 검증) */
export function Stepper({
  value,
  min,
  max,
  onChange,
  label,
  decrementLabel,
  incrementLabel,
}: StepperProps) {
  const clamp = (next: number) => Math.min(max, Math.max(min, next));

  return (
    <div className="flex items-center gap-4" role="group" aria-label={label}>
      <button
        type="button"
        aria-label={decrementLabel}
        disabled={value <= min}
        onClick={() => onChange(clamp(value - 1))}
        className="h-11 w-11 rounded-full border border-[#D7DEEA] bg-white text-xl font-bold text-ink-600 disabled:opacity-30"
      >
        −
      </button>
      <output aria-live="polite" className="min-w-10 text-center text-2xl font-extrabold text-navy-900">
        {value}
      </output>
      <button
        type="button"
        aria-label={incrementLabel}
        disabled={value >= max}
        onClick={() => onChange(clamp(value + 1))}
        className="h-11 w-11 rounded-full border border-[#D7DEEA] bg-white text-xl font-bold text-ink-600 disabled:opacity-30"
      >
        +
      </button>
    </div>
  );
}
