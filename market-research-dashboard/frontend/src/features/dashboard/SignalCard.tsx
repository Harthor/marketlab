// MarketLab Dashboard v2 — SignalCard (spec §4.6, §5.2)

import { ChevronRight } from 'lucide-react';
import type { DashboardMode, SignalCardData } from '@/types/dashboard';
import { getStateStyles } from '@/utils/statePresentation';
import SignalIcon from './SignalIcon';
import StateBadge from './StateBadge';
import ConfidenceMeter from './ConfidenceMeter';

interface SignalCardProps {
  signal: SignalCardData;
  mode: DashboardMode;
  selected: boolean;
  onSelect: () => void;
}

const freqLabel: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  insufficient: 'Blocked',
};

export default function SignalCard({ signal, mode, selected, onSelect }: SignalCardProps) {
  const styles = getStateStyles(signal.state);
  const narrative = signal.narrative[mode];
  const isBlocked = signal.state === 'blocked';

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`
        group relative flex flex-col text-left w-full
        rounded-card border bg-ml-bg-card shadow-ml-card
        p-4 md:p-5 transition-all duration-[160ms] ease-out
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ml-border-strong
        motion-safe:hover:-translate-y-0.5 motion-safe:hover:shadow-ml-card-hover
        ${selected ? `ring-1 ring-offset-0 ${styles.ring} ${styles.border}` : 'border-ml-border hover:' + styles.border}
        min-h-[260px] md:min-h-[292px]
      `}
    >
      {/* ── Header row ──────────────────────────────────── */}
      <div className="flex items-center gap-2 mb-1">
        <span className={`w-2 h-2 rounded-full shrink-0 ${styles.dot}`} />
        <SignalIcon icon={signal.icon} className={styles.text} size={16} />
        <span className="text-sm md:text-base font-semibold text-ml-text-primary truncate flex-1">
          {narrative.title}
        </span>
        <span className={`text-[11px] font-medium px-2 py-0.5 rounded-chip ${styles.bg} ${styles.text}`}>
          {freqLabel[signal.dataFrequency] ?? signal.dataFrequency}
        </span>
      </div>

      {/* ── Subtitle ────────────────────────────────────── */}
      <p className="text-xs md:text-sm text-ml-text-muted mb-3">
        {narrative.subtitle}
      </p>

      {/* ── Summary ─────────────────────────────────────── */}
      <p className="text-sm md:text-[15px] leading-relaxed text-ml-text-secondary mb-4 line-clamp-3 flex-1">
        {narrative.summary}
      </p>

      {/* ── Confidence / Progress ───────────────────────── */}
      {isBlocked && signal.progress ? (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-ml-text-muted">Progreso</span>
            <span className="text-xs font-mono text-ml-text-secondary">
              {signal.progress.current}/{signal.progress.required} {signal.progress.unit === 'days' ? 'dias' : signal.progress.unit}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-ml-bg-elevated overflow-hidden">
            <div
              className={`h-full rounded-full ${styles.dot} transition-all duration-300`}
              style={{ width: `${Math.min((signal.progress.current / signal.progress.required) * 100, 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <div className="mb-3">
          <ConfidenceMeter value={signal.confidence} state={signal.state} />
        </div>
      )}

      {/* ── Secondary row (Simple) ──────────────────────── */}
      {mode === 'simple' && !isBlocked && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ml-text-muted mb-3">
          {signal.cardKey === 'trends' && (
            <span>Uso: senal principal</span>
          )}
          {signal.cardKey === 'fng' && (
            <span>Uso: indicador de contexto</span>
          )}
          {signal.sampleSize != null && signal.minSampleRequired != null && (
            <span>Datos: {signal.sampleSize}/{signal.minSampleRequired}</span>
          )}
          {signal.bestLead && (
            <span>Mejor hallazgo: {signal.bestLead.label} | r={signal.bestLead.correlation.toFixed(2)}</span>
          )}
        </div>
      )}

      {/* ── Secondary row (Pro) ─────────────────────────── */}
      {mode === 'pro' && !isBlocked && signal.bestLead && (
        <div className="space-y-1 text-xs font-mono text-ml-text-secondary mb-3">
          <div className="flex flex-wrap gap-x-2">
            <span>r={signal.bestLead.correlation.toFixed(2)}</span>
            {signal.bestLead.pValue != null && (
              <span>p={signal.bestLead.pValue < 0.001 ? '<0.001' : signal.bestLead.pValue.toFixed(3)}</span>
            )}
            <span>{signal.bestLead.label}</span>
            {signal.stats?.stabilityScore != null && (
              <span>stability {signal.stats.stabilityScore}/100</span>
            )}
          </div>
          {signal.secondaryFindings && signal.secondaryFindings.length > 0 && (
            <div className="flex flex-wrap gap-x-2 text-ml-text-muted">
              {signal.secondaryFindings.map((f) => (
                <span key={f.signalId}>
                  {f.lead.label} {f.label.toLowerCase()} r={f.lead.correlation.toFixed(2)}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Pro advanced block ──────────────────────────── */}
      {mode === 'pro' && !isBlocked && (
        <div className="flex flex-wrap gap-x-3 text-[11px] text-ml-text-muted mb-3">
          {signal.detail?.granger && (
            <span>Granger: {signal.detail.granger.direction}</span>
          )}
          {signal.detail?.regimeBreakdown && signal.detail.regimeBreakdown.length > 0 && (
            signal.detail.regimeBreakdown.map((r) => (
              <span key={r.name}>
                {r.name}: {r.correlation != null ? r.correlation.toFixed(2) : '--'}
              </span>
            ))
          )}
        </div>
      )}

      {/* ── Blocked status line ─────────────────────────── */}
      {isBlocked && (
        <div className="text-xs text-ml-text-muted mb-3">
          Estado: aun no analizable
        </div>
      )}

      {/* ── CTA footer ──────────────────────────────────── */}
      <div className="flex items-center justify-between mt-auto pt-2 border-t border-ml-border/50">
        <span className={`text-sm font-medium ${styles.text}`}>
          {narrative.cta}
        </span>
        <ChevronRight size={16} className={`${styles.text} transition-transform duration-150 group-hover:translate-x-0.5`} />
      </div>
    </button>
  );
}
