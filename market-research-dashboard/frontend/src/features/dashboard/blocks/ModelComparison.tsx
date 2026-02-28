// MarketLab Dashboard v2 — ModelComparison (spec §13.3)

import type { ForecastModelRow } from '@/types/dashboard';

interface ModelComparisonProps {
  models: ForecastModelRow[];
}

export default function ModelComparison({ models }: ModelComparisonProps) {
  if (!models || models.length === 0) return null;

  // Find best by Sharpe
  const bestSharpe = Math.max(...models.map((m) => m.sharpe ?? -Infinity));

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Comparacion de modelos</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ml-text-muted border-b border-ml-border">
              <th className="text-left py-2 font-medium">Modelo</th>
              <th className="text-right py-2 font-medium">Sharpe</th>
              <th className="text-right py-2 font-medium">CAGR</th>
              <th className="text-right py-2 font-medium">Max DD</th>
              <th className="text-right py-2 font-medium">Hit Rate</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => {
              const isBest = m.sharpe === bestSharpe;
              return (
                <tr
                  key={m.modelId}
                  className={`border-b border-ml-border/30 ${isBest ? 'bg-[var(--ml-green-soft)]' : ''}`}
                >
                  <td className={`py-2 font-medium ${isBest ? 'text-[#86EFAC]' : 'text-ml-text-secondary'}`}>
                    {m.label}
                  </td>
                  <td className="py-2 text-right font-mono text-ml-text-primary">
                    {m.sharpe != null ? m.sharpe.toFixed(2) : '--'}
                  </td>
                  <td className="py-2 text-right font-mono text-ml-text-primary">
                    {m.cagr != null ? `${m.cagr.toFixed(2)}%` : '--'}
                  </td>
                  <td className="py-2 text-right font-mono text-ml-text-primary">
                    {m.maxDrawdown != null ? `${m.maxDrawdown.toFixed(1)}%` : '--'}
                  </td>
                  <td className="py-2 text-right font-mono text-ml-text-primary">
                    {m.hitRate != null ? `${(m.hitRate * 100).toFixed(0)}%` : '--'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
