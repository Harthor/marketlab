// MarketLab Dashboard v2 — ForecastPanel (spec §13)

import { useState, lazy, Suspense } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { DashboardMode, ForecastPanelData } from '@/types/dashboard';
import { SkeletonChart } from './Skeleton';

const EquityCurve = lazy(() => import('./charts/EquityCurve'));
const ModelComparison = lazy(() => import('./blocks/ModelComparison'));

interface ForecastPanelProps {
  forecast: ForecastPanelData;
  mode: DashboardMode;
}

export default function ForecastPanel({ forecast, mode }: ForecastPanelProps) {
  const [expanded, setExpanded] = useState(true);

  if (!forecast.available) return null;

  return (
    <div className="rounded-card border border-ml-border bg-ml-bg-surface p-4 md:p-6 space-y-4">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full group"
      >
        <h3 className="text-base md:text-lg font-semibold text-ml-text-primary">
          Modelos y backtests
        </h3>
        {expanded ? (
          <ChevronUp size={18} className="text-ml-text-muted group-hover:text-ml-text-secondary transition-colors" />
        ) : (
          <ChevronDown size={18} className="text-ml-text-muted group-hover:text-ml-text-secondary transition-colors" />
        )}
      </button>

      {expanded && (
        <div className="space-y-5">
          {/* Equity curve */}
          <Suspense fallback={<SkeletonChart />}>
            <EquityCurve data={forecast.equityCurve} />
          </Suspense>

          {/* Model comparison table */}
          <Suspense fallback={<SkeletonChart />}>
            <ModelComparison models={forecast.models} />
          </Suspense>
        </div>
      )}
    </div>
  );
}
