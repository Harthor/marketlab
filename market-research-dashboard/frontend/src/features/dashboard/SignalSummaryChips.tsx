// MarketLab Dashboard — SignalSummaryChips (state summary bar)

import type { SignalCardData, SignalState } from '@/types/dashboard';
import { statePresentation, getStateStyles } from '@/utils/statePresentation';

interface SignalSummaryChipsProps {
  signals: SignalCardData[];
}

export default function SignalSummaryChips({ signals }: SignalSummaryChipsProps) {
  // Count signals per state
  const counts: Partial<Record<SignalState, number>> = {};
  for (const s of signals) {
    counts[s.state] = (counts[s.state] ?? 0) + 1;
  }

  const states: SignalState[] = ['green', 'yellow', 'orange', 'red', 'blocked'];

  return (
    <div className="signal-summary-bar">
      {states
        .filter((st) => (counts[st] ?? 0) > 0)
        .map((st) => {
          const styles = getStateStyles(st);
          return (
            <span key={st} className="signal-summary-chip">
              <span className={`signal-summary-chip__dot ${styles.dot}`} />
              {statePresentation[st].badgeLabelEs}
              <span className="signal-summary-chip__count">{counts[st]}</span>
            </span>
          );
        })}
    </div>
  );
}
