// MarketLab Dashboard v2 — DashboardHeader (compact, Degen-style)

import type { DashboardMode } from '@/types/dashboard';
import ModeToggle from './ModeToggle';

interface DashboardHeaderProps {
  asset: string;
  generatedAt: string;
  signalCount: number;
  mode: DashboardMode;
  onModeChange: (mode: DashboardMode) => void;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('es-AR', {
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function DashboardHeader({ asset, generatedAt, signalCount, mode, onModeChange }: DashboardHeaderProps) {
  return (
    <div className="degen-header" style={{ marginBottom: '0.75rem' }}>
      <h2>{asset} Signal Dashboard</h2>
      <div className="degen-header__meta">
        <span>{signalCount} signals tracked</span>
        <span className="degen-header__ts">Updated: {formatDate(generatedAt)}</span>
      </div>
      <div style={{ marginLeft: 'auto' }}>
        <ModeToggle value={mode} onChange={onModeChange} />
      </div>
    </div>
  );
}
