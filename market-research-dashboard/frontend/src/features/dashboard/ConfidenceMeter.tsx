// MarketLab Dashboard v2 — ConfidenceMeter (spec §4.7)

import type { SignalState } from '@/types/dashboard';
import { getStateStyles } from '@/utils/statePresentation';

interface ConfidenceMeterProps {
  value: number;
  state: SignalState;
}

const TOTAL_SEGMENTS = 10;

export default function ConfidenceMeter({ value, state }: ConfidenceMeterProps) {
  const styles = getStateStyles(state);
  const filled = Math.round((value / 100) * TOTAL_SEGMENTS);

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-ml-text-muted shrink-0">Confianza</span>
      <div className="flex gap-[3px] flex-1">
        {Array.from({ length: TOTAL_SEGMENTS }, (_, i) => (
          <div
            key={i}
            className={`h-2 flex-1 rounded-sm transition-colors duration-150 ${
              i < filled ? styles.dot : 'bg-ml-bg-elevated'
            }`}
          />
        ))}
      </div>
      <span className={`text-xs font-mono font-medium tabular-nums ${styles.text}`}>
        {value}%
      </span>
    </div>
  );
}
