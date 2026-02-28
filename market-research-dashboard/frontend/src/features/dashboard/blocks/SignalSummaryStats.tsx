// MarketLab Dashboard v2 — SignalSummaryStats (spec §7.4.1)

import type { SignalCardData } from '@/types/dashboard';

interface SignalSummaryStatsProps {
  signal: SignalCardData;
}

export default function SignalSummaryStats({ signal }: SignalSummaryStatsProps) {
  const lead = signal.bestLead;
  if (!lead) return null;

  const stats = [
    { label: 'Best lead', value: lead.label },
    { label: 'r', value: lead.correlation.toFixed(2) },
    { label: 'p-value', value: lead.pValue != null ? (lead.pValue < 0.001 ? '<0.001' : lead.pValue.toFixed(3)) : '--' },
    { label: 'Type', value: lead.kind },
    { label: 'Freq', value: signal.dataFrequency },
    ...(signal.sampleSize != null ? [{ label: 'N', value: String(signal.sampleSize) }] : []),
  ];

  return (
    <div className="flex flex-wrap gap-x-4 gap-y-2 py-3 px-4 rounded-lg bg-ml-bg-elevated border border-ml-border">
      {stats.map((s) => (
        <div key={s.label} className="flex items-center gap-1.5">
          <span className="text-[11px] text-ml-text-muted uppercase tracking-wide">{s.label}</span>
          <span className="text-sm font-mono font-medium text-ml-text-primary">{s.value}</span>
        </div>
      ))}
    </div>
  );
}
