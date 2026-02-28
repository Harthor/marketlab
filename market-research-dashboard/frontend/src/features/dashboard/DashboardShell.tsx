// MarketLab Dashboard v2 — DashboardShell (spec §4.2)

import type { ReactNode } from 'react';

interface DashboardShellProps {
  header: ReactNode;
  grid: ReactNode;
  detail: ReactNode;
  forecast?: ReactNode;
}

export default function DashboardShell({ header, grid, detail, forecast }: DashboardShellProps) {
  return (
    <div className="min-h-screen bg-ml-bg-canvas text-ml-text-primary font-sans">
      <div className="mx-auto max-w-[1440px] px-4 md:px-6 xl:px-8 py-4 md:py-6">
        {/* Header */}
        {header}

        {/* Main content: grid + detail */}
        <div className="flex flex-col lg:grid lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:gap-6">
          {/* Left: signal cards */}
          <div className="mb-4 lg:mb-0">
            {grid}
          </div>

          {/* Right: detail panel */}
          <div className="lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:scrollbar-thin">
            {detail}
          </div>
        </div>

        {/* Forecast (full width) */}
        {forecast && (
          <div className="mt-6">
            {forecast}
          </div>
        )}
      </div>
    </div>
  );
}
