// MarketLab Dashboard v2 — BootstrapConfidence (spec §7.4.6)

import type { BootstrapMetric } from '@/types/dashboard';

interface BootstrapConfidenceProps {
  bootstrap?: BootstrapMetric | null;
}

export default function BootstrapConfidence({ bootstrap }: BootstrapConfidenceProps) {
  if (!bootstrap || !bootstrap.available) {
    return (
      <div className="flex items-center gap-2 py-2">
        <span className="text-xs text-ml-text-muted uppercase tracking-wide font-medium">Bootstrap</span>
        <span className="text-xs text-ml-text-muted italic">Pendiente</span>
      </div>
    );
  }

  const chips = [
    bootstrap.pValueMaxStat != null && {
      label: 'Bootstrap p',
      value: bootstrap.pValueMaxStat < 0.001 ? '<0.001' : bootstrap.pValueMaxStat.toFixed(3),
    },
    bootstrap.ciLow != null && bootstrap.ciHigh != null && {
      label: '95% CI',
      value: `[${bootstrap.ciLow!.toFixed(2)}, ${bootstrap.ciHigh!.toFixed(2)}]`,
    },
    { label: 'Max-stat', value: bootstrap.pValueMaxStat != null ? 'yes' : 'no' },
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Bootstrap</h4>
      <div className="flex flex-wrap gap-2">
        {chips.map((chip) => (
          <span
            key={chip.label}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-chip bg-ml-bg-elevated border border-ml-border text-xs"
          >
            <span className="text-ml-text-muted">{chip.label}</span>
            <span className="font-mono text-ml-text-primary">{chip.value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
