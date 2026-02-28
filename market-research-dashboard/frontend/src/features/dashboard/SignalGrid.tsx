// MarketLab Dashboard v2 — SignalGrid (spec §4.5)

import type { DashboardMode, SignalCardData, SignalCardKey } from '@/types/dashboard';
import SignalCard from './SignalCard';

interface SignalGridProps {
  signals: SignalCardData[];
  selectedSignal: SignalCardKey;
  onSelect: (key: SignalCardKey) => void;
  mode: DashboardMode;
}

export default function SignalGrid({ signals, selectedSignal, onSelect, mode }: SignalGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-5">
      {signals.map((signal) => (
        <SignalCard
          key={signal.cardKey}
          signal={signal}
          mode={mode}
          selected={signal.cardKey === selectedSignal}
          onSelect={() => onSelect(signal.cardKey)}
        />
      ))}
    </div>
  );
}
