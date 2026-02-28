// MarketLab Dashboard v2 — ModeToggle (spec §4.4)

import type { DashboardMode } from '@/types/dashboard';

interface ModeToggleProps {
  value: DashboardMode;
  onChange: (value: DashboardMode) => void;
}

export default function ModeToggle({ value, onChange }: ModeToggleProps) {
  return (
    <div className="relative flex rounded-chip bg-ml-bg-elevated p-1 w-full md:w-auto">
      {/* Sliding pill */}
      <div
        className="absolute top-1 bottom-1 rounded-chip bg-ml-bg-card shadow-md transition-transform duration-[220ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
        style={{
          width: 'calc(50% - 4px)',
          transform: value === 'pro' ? 'translateX(calc(100% + 4px))' : 'translateX(0)',
        }}
      />

      <button
        type="button"
        role="radio"
        aria-checked={value === 'simple'}
        onClick={() => onChange('simple')}
        className={`relative z-10 flex-1 px-5 py-1.5 text-sm font-medium rounded-chip transition-colors duration-[220ms] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ml-border-strong ${
          value === 'simple' ? 'text-ml-text-primary' : 'text-ml-text-muted hover:text-ml-text-secondary'
        }`}
      >
        Simple
      </button>

      <button
        type="button"
        role="radio"
        aria-checked={value === 'pro'}
        onClick={() => onChange('pro')}
        className={`relative z-10 flex-1 px-5 py-1.5 text-sm font-medium rounded-chip transition-colors duration-[220ms] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ml-border-strong ${
          value === 'pro' ? 'text-ml-text-primary' : 'text-ml-text-muted hover:text-ml-text-secondary'
        }`}
      >
        Pro
      </button>
    </div>
  );
}
