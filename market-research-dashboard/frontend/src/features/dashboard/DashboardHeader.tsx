// MarketLab Dashboard v2 — DashboardHeader (spec §4.3)

import type { DashboardMode } from '@/types/dashboard';
import ModeToggle from './ModeToggle';

interface DashboardHeaderProps {
  asset: string;
  generatedAt: string;
  mode: DashboardMode;
  onModeChange: (mode: DashboardMode) => void;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('es-AR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
    }) + ' UTC';
  } catch {
    return iso;
  }
}

export default function DashboardHeader({ asset, generatedAt, mode, onModeChange }: DashboardHeaderProps) {
  return (
    <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 md:gap-4 pb-4 md:pb-6">
      {/* Left */}
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-3">
          <h1 className="text-xl md:text-2xl font-bold text-ml-text-primary tracking-tight">
            MarketLab
          </h1>
          <span className="px-2.5 py-0.5 text-xs font-semibold rounded-chip bg-ml-bg-elevated text-ml-text-secondary border border-ml-border">
            {asset}
          </span>
        </div>
        <p className="text-xs md:text-sm text-ml-text-muted">
          BTC signal dashboard &middot; Ultima actualizacion: {formatDate(generatedAt)}
        </p>
      </div>

      {/* Right */}
      <div className="w-full md:w-auto">
        <ModeToggle value={mode} onChange={onModeChange} />
      </div>
    </header>
  );
}
