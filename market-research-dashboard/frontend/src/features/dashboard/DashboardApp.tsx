// MarketLab Dashboard v2 — DashboardApp (table layout like Degen Scanner)

import '@/styles/dashboard-table.css';

import { useState, lazy, Suspense } from 'react';
import type { DashboardMode, SignalCardKey } from '@/types/dashboard';
import { useDashboardRun } from './hooks/useDashboardRun';
import DashboardShell from './DashboardShell';
import DashboardHeader from './DashboardHeader';
import SignalTable from './SignalTable';
import SignalSummaryChips from './SignalSummaryChips';
import { SkeletonChart } from './Skeleton';

const DetailPanel = lazy(() => import('./DetailPanel'));
const ForecastPanel = lazy(() => import('./ForecastPanel'));

export default function DashboardApp() {
  const { run, loading } = useDashboardRun();
  const [mode, setMode] = useState<DashboardMode>(run.modeDefault ?? 'simple');
  const [selectedSignal, setSelectedSignal] = useState<SignalCardKey>(
    run.selectedSignalCardKey ?? run.signals[0]?.cardKey ?? 'trends'
  );

  const selectedSignalData = run.signals.find((s) => s.cardKey === selectedSignal) ?? run.signals[0];

  if (loading && !run.signals.length) {
    return (
      <div className="dashboard-page">
        <div className="degen-loading">Cargando señales...</div>
      </div>
    );
  }

  return (
    <DashboardShell
      header={
        <DashboardHeader
          asset={run.asset}
          generatedAt={run.generatedAt}
          signalCount={run.signals.length}
          mode={mode}
          onModeChange={setMode}
        />
      }
      chips={<SignalSummaryChips signals={run.signals} />}
      table={
        <SignalTable
          signals={run.signals}
          selected={selectedSignal}
          onSelect={setSelectedSignal}
          mode={mode}
        />
      }
      detail={
        <Suspense fallback={<div className="space-y-4"><SkeletonChart /><SkeletonChart /></div>}>
          {selectedSignalData && (
            <div className="signal-detail-section">
              <DetailPanel signal={selectedSignalData} mode={mode} />
            </div>
          )}
        </Suspense>
      }
      forecast={
        run.forecast?.available ? (
          <Suspense fallback={<SkeletonChart />}>
            <ForecastPanel forecast={run.forecast} mode={mode} />
          </Suspense>
        ) : null
      }
    />
  );
}
