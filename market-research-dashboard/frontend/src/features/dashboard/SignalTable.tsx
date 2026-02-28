// MarketLab Dashboard — SignalTable (table view like Degen Scanner)

import type { SignalCardData, SignalCardKey, DashboardMode } from '@/types/dashboard';
import StateBadge from './StateBadge';
import SignalIcon from './SignalIcon';

interface SignalTableProps {
  signals: SignalCardData[];
  selected: SignalCardKey | null;
  onSelect: (key: SignalCardKey) => void;
  mode: DashboardMode;
}

function formatLead(signal: SignalCardData): string {
  if (!signal.bestLead) return '—';
  const sign = signal.bestLead.value > 0 ? '+' : '';
  return `${sign}${signal.bestLead.value}${signal.bestLead.unit === 'week' ? 'w' : 'd'}`;
}

function formatCorrelation(signal: SignalCardData): string {
  const r = signal.stats?.primaryCorrelation ?? signal.bestLead?.correlation;
  if (r == null) return '—';
  return r.toFixed(2);
}

function formatFreq(freq: string): string {
  switch (freq) {
    case 'weekly': return 'Weekly';
    case 'daily': return 'Daily';
    default: return '—';
  }
}

export default function SignalTable({ signals, selected, onSelect, mode }: SignalTableProps) {
  return (
    <div className="signal-table-wrap">
      <table className="signal-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Signal</th>
            <th>Freq</th>
            <th>Estado</th>
            <th>Correlación</th>
            <th>Confianza</th>
            <th>Best Lead</th>
            {mode === 'pro' && <th>p-value</th>}
            <th>N (obs)</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal, i) => {
            const isSelected = signal.cardKey === selected;
            const pVal = signal.stats?.primaryPValue;
            return (
              <tr
                key={signal.cardKey}
                className={`signal-table__row ${isSelected ? 'signal-table__row--selected' : ''}`}
                onClick={() => onSelect(signal.cardKey)}
              >
                <td className="signal-table__rank">{i + 1}</td>
                <td>
                  <div className="signal-table__signal">
                    <SignalIcon icon={signal.icon} size={16} />
                    <span className="signal-table__signal-name">{signal.displayName}</span>
                    <span className="signal-table__signal-sub">{signal.simpleName}</span>
                  </div>
                </td>
                <td>
                  <span className="signal-table__freq">{formatFreq(signal.dataFrequency)}</span>
                </td>
                <td>
                  <StateBadge state={signal.state} size="sm" />
                </td>
                <td className="signal-table__mono">{formatCorrelation(signal)}</td>
                <td>
                  <div className="signal-table__confidence">
                    <div className="signal-table__conf-bar">
                      <div
                        className="signal-table__conf-fill"
                        style={{ width: `${signal.confidence}%` }}
                        data-state={signal.state}
                      />
                    </div>
                    <span className="signal-table__conf-value">{signal.confidence}%</span>
                  </div>
                </td>
                <td className="signal-table__mono">{formatLead(signal)}</td>
                {mode === 'pro' && (
                  <td className="signal-table__mono">
                    {pVal != null ? pVal.toFixed(3) : '—'}
                  </td>
                )}
                <td className="signal-table__mono">
                  {signal.sampleSize != null ? `${signal.sampleSize}` : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
