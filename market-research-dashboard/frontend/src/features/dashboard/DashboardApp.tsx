// MarketLab Dashboard v2 — DashboardApp (spec §4.2)

import { useState, lazy, Suspense } from 'react';
import type { DashboardMode, SignalCardKey } from '@/types/dashboard';
import { useDashboardRun } from './hooks/useDashboardRun';
import DashboardShell from './DashboardShell';
import DashboardHeader from './DashboardHeader';
import SignalGrid from './SignalGrid';
import { SkeletonCard, SkeletonChart } from './Skeleton';

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
      <div className="min-h-screen bg-ml-bg-canvas text-ml-text-primary font-sans">
        <div className="mx-auto max-w-[1440px] px-4 md:px-6 xl:px-8 py-4 md:py-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </div>
      </div>
    );
  }

  return (
    <DashboardShell
      header={
        <DashboardHeader
          asset={run.asset}
          generatedAt={run.generatedAt}
          mode={mode}
          onModeChange={setMode}
        />
      }
      grid={
        <SignalGrid
          signals={run.signals}
          selectedSignal={selectedSignal}
          onSelect={setSelectedSignal}
          mode={mode}
        />
      }
      detail={
        <Suspense fallback={<div className="space-y-4"><SkeletonChart /><SkeletonChart /></div>}>
          {selectedSignalData && (
            <DetailPanel signal={selectedSignalData} mode={mode} />
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
