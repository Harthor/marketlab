// MarketLab Dashboard v2 — StabilityScore (spec §7.4.7)

import type { ConfidenceBreakdown, SignalState } from '@/types/dashboard';
import { getStateStyles } from '@/utils/statePresentation';

interface StabilityScoreProps {
  breakdown?: ConfidenceBreakdown | null;
  state: SignalState;
}

const componentLabels: Array<{ key: keyof ConfidenceBreakdown; label: string }> = [
  { key: 'strength', label: 'Fuerza' },
  { key: 'consistency', label: 'Consistencia' },
  { key: 'regimeRobustness', label: 'Regimen' },
  { key: 'significance', label: 'Significancia' },
  { key: 'sampleSufficiency', label: 'Muestra' },
];

export default function StabilityScore({ breakdown, state }: StabilityScoreProps) {
  if (!breakdown) {
    return (
      <div className="text-xs text-ml-text-muted italic py-2">
        Score de estabilidad: pendiente
      </div>
    );
  }

  const styles = getStateStyles(state);

  return (
    <div className="space-y-3">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Score de estabilidad</h4>

      <div className="flex items-center gap-4">
        {/* Score circle */}
        <div className="relative w-16 h-16 shrink-0">
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle
              cx="18" cy="18" r="14"
              fill="none"
              stroke="var(--ml-border-default)"
              strokeWidth="3"
            />
            <circle
              cx="18" cy="18" r="14"
              fill="none"
              stroke={styles.base}
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={`${(breakdown.total / 100) * 88} 88`}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className={`text-sm font-bold font-mono ${styles.text}`}>{breakdown.total}</span>
          </div>
        </div>

        {/* Component bars */}
        <div className="flex-1 space-y-1.5">
          {componentLabels.map(({ key, label }) => {
            const val = breakdown[key] as number | undefined;
            if (val == null) return null;
            return (
              <div key={key} className="flex items-center gap-2">
                <span className="text-[10px] text-ml-text-muted w-20 truncate">{label}</span>
                <div className="flex-1 h-1.5 rounded-full bg-ml-bg-elevated overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{ width: `${val}%`, backgroundColor: styles.base }}
                  />
                </div>
                <span className="text-[10px] font-mono text-ml-text-muted w-6 text-right">{val}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
