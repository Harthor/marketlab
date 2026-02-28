// MarketLab Dashboard v2 — DetailPanel (spec §4.8, §7)

import { lazy, Suspense } from 'react';
import type { DashboardMode, SignalCardData } from '@/types/dashboard';
import { getStateStyles } from '@/utils/statePresentation';
import SignalIcon from './SignalIcon';
import StateBadge from './StateBadge';
import { SkeletonChart } from './Skeleton';
import BlockedDetailState from './BlockedDetailState';

// Lazy-loaded sub-components
const CorrelationChart = lazy(() => import('./charts/CorrelationChart'));
const LagProfile = lazy(() => import('./charts/LagProfile'));
const RollingCorrelation = lazy(() => import('./charts/RollingCorrelation'));
const SignalSummaryStats = lazy(() => import('./blocks/SignalSummaryStats'));
const RegimeBreakdown = lazy(() => import('./blocks/RegimeBreakdown'));
const GrangerDirection = lazy(() => import('./blocks/GrangerDirection'));
const BootstrapConfidence = lazy(() => import('./blocks/BootstrapConfidence'));
const StabilityScore = lazy(() => import('./blocks/StabilityScore'));
const TimelineNarrative = lazy(() => import('./blocks/TimelineNarrative'));

interface DetailPanelProps {
  signal: SignalCardData;
  mode: DashboardMode;
}

const analogies: Record<string, string> = {
  trends: 'Es como mirar cuanta gente busca paraguas antes de que empiece a llover.',
  fng: 'Es como un termometro que sube despues de que la habitacion ya se calento.',
  rss: 'Es como escuchar mas ruido en las noticias antes de que el mercado termine de reaccionar.',
  reddit: 'Todavia no hay suficientes conversaciones guardadas como para saber si la multitud llega antes o despues.',
};

const humanSummaries: Record<string, string> = {
  trends: 'Cuando mas gente busca Bitcoin, el precio suele moverse 1-2 semanas despues.',
  fng: 'Este indice suele reaccionar al precio; sirve para saber como se siente el mercado, no para adivinar el proximo movimiento.',
  rss: 'Las noticias parecen empezar a mostrar relacion con el precio, pero todavia necesitamos mas historial.',
  reddit: 'Todavia estamos juntando datos; por ahora no conviene sacar conclusiones.',
};

export default function DetailPanel({ signal, mode }: DetailPanelProps) {
  const styles = getStateStyles(signal.state);
  const narrative = signal.narrative[mode];
  const isBlocked = signal.state === 'blocked';
  const detail = signal.detail;

  return (
    <div className="rounded-card border border-ml-border bg-ml-bg-surface p-4 md:p-6 space-y-5">
      {/* ── Header ──────────────────────────────────────── */}
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-lg ${styles.bg}`}>
          <SignalIcon icon={signal.icon} className={styles.text} size={20} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-base md:text-lg font-semibold text-ml-text-primary">
              {narrative.title}
            </h2>
            <StateBadge state={signal.state} size="sm" />
          </div>
          <p className="text-xs md:text-sm text-ml-text-muted mt-0.5">
            {narrative.subtitle}
          </p>
        </div>
      </div>

      {/* ── Summary ─────────────────────────────────────── */}
      <p className="text-sm leading-relaxed text-ml-text-secondary">
        {narrative.summary}
      </p>

      {/* ── Blocked state ───────────────────────────────── */}
      {isBlocked ? (
        <BlockedDetailState signal={signal} />
      ) : mode === 'simple' ? (
        /* ── Simple mode content ────────────────────────── */
        <div className="space-y-5">
          {/* Human summary */}
          <div className="space-y-1">
            <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Resumen</h4>
            <p className="text-sm text-ml-text-secondary leading-relaxed">
              {humanSummaries[signal.cardKey] ?? narrative.summary}
            </p>
          </div>

          {/* Correlation chart */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && <CorrelationChart detail={detail} />}
          </Suspense>

          {/* What does this mean? */}
          <div className="space-y-1">
            <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">
              Que significa esto?
            </h4>
            <p className="text-sm text-ml-text-secondary italic leading-relaxed">
              {analogies[signal.cardKey] ?? ''}
            </p>
          </div>

          {/* Timeline */}
          <Suspense fallback={<SkeletonChart />}>
            <TimelineNarrative cardKey={signal.cardKey} />
          </Suspense>

          {/* Data quality notes */}
          {signal.dataQualityNotes && signal.dataQualityNotes.length > 0 && (
            <div className="space-y-1.5">
              <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Notas</h4>
              <div className="flex flex-wrap gap-1.5">
                {signal.dataQualityNotes.map((note) => (
                  <span
                    key={note.code}
                    className="px-2 py-0.5 text-[11px] rounded-chip bg-ml-bg-elevated border border-ml-border text-ml-text-muted"
                  >
                    {note.message}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* ── Pro mode content ───────────────────────────── */
        <div className="space-y-5">
          {/* Summary stats */}
          <Suspense fallback={<SkeletonChart />}>
            <SignalSummaryStats signal={signal} />
          </Suspense>

          {/* Lag profile */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && <LagProfile points={detail.lagProfile} bestLead={detail.selectedLead} mode={mode} />}
          </Suspense>

          {/* Rolling correlation */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && <RollingCorrelation points={detail.rollingCorrelation} signal={signal} />}
          </Suspense>

          {/* Regime breakdown */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && <RegimeBreakdown regimes={detail.regimeBreakdown} />}
          </Suspense>

          {/* Granger direction */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && <GrangerDirection granger={detail.granger} />}
          </Suspense>

          {/* Bootstrap confidence */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && <BootstrapConfidence bootstrap={detail.bootstrap} />}
          </Suspense>

          {/* Stability score */}
          <Suspense fallback={<SkeletonChart />}>
            {detail && (
              <StabilityScore breakdown={detail.confidenceBreakdown} state={signal.state} />
            )}
          </Suspense>

          {/* Data quality notes */}
          {signal.dataQualityNotes && signal.dataQualityNotes.length > 0 && (
            <div className="space-y-1.5">
              <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Calidad de datos</h4>
              <div className="flex flex-wrap gap-1.5">
                {signal.dataQualityNotes.map((note) => (
                  <span
                    key={note.code}
                    className="px-2 py-0.5 text-[11px] rounded-chip bg-ml-bg-elevated border border-ml-border text-ml-text-muted"
                  >
                    {note.message}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
