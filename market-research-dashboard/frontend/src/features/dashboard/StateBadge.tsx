// MarketLab Dashboard v2 — StateBadge (spec §5.1)

import type { SignalState } from '@/types/dashboard';
import { getStateStyles, statePresentation } from '@/utils/statePresentation';

interface StateBadgeProps {
  state: SignalState;
  size?: 'sm' | 'md';
}

export default function StateBadge({ state, size = 'md' }: StateBadgeProps) {
  const styles = getStateStyles(state);
  const label = statePresentation[state].badgeLabelEs;
  const dotSize = size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2';
  const textSize = size === 'sm' ? 'text-[11px]' : 'text-xs';

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-chip ${styles.bg} ${styles.border} border`}>
      <span className={`${dotSize} rounded-full ${styles.dot} shrink-0`} />
      <span className={`${textSize} font-medium ${styles.text}`}>
        {label}
      </span>
    </span>
  );
}
