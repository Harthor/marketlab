// MarketLab Dashboard v2 — RegimeBreakdown (spec §7.4.4)

import type { RegimeMetric } from '@/types/dashboard';

interface RegimeBreakdownProps {
  regimes?: RegimeMetric[];
}

const regimeLabels: Record<string, string> = {
  bull: 'Bull',
  bear: 'Bear',
  fear: 'Extreme fear',
  greed: 'Extreme greed',
  high_vol: 'High vol',
  low_vol: 'Low vol',
};

export default function RegimeBreakdown({ regimes }: RegimeBreakdownProps) {
  if (!regimes || regimes.length === 0) {
    return (
      <div className="text-xs text-ml-text-muted italic py-2">
        Regimenes: pendiente
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Regimenes</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ml-text-muted border-b border-ml-border">
              <th className="text-left py-1.5 font-medium">Regime</th>
              <th className="text-right py-1.5 font-medium">Corr</th>
              <th className="text-right py-1.5 font-medium">p-value</th>
              {regimes.some((r) => r.n != null) && (
                <th className="text-right py-1.5 font-medium">N</th>
              )}
            </tr>
          </thead>
          <tbody>
            {regimes.map((r) => (
              <tr key={r.name} className="border-b border-ml-border/30">
                <td className="py-1.5 text-ml-text-secondary">{regimeLabels[r.name] ?? r.name}</td>
                <td className="py-1.5 text-right font-mono text-ml-text-primary">
                  {r.correlation != null ? r.correlation.toFixed(2) : '--'}
                </td>
                <td className="py-1.5 text-right font-mono text-ml-text-muted">
                  {r.pValue != null ? (r.pValue < 0.001 ? '<0.001' : r.pValue.toFixed(3)) : '--'}
                </td>
                {regimes.some((regime) => regime.n != null) && (
                  <td className="py-1.5 text-right font-mono text-ml-text-muted">
                    {r.n ?? '--'}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
