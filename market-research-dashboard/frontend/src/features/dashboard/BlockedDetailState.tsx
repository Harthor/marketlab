// MarketLab Dashboard v2 — BlockedDetailState (spec §7.4.8)

import { AlertCircle, CheckCircle2, Circle } from 'lucide-react';
import type { SignalCardData } from '@/types/dashboard';

interface BlockedDetailStateProps {
  signal: SignalCardData;
}

export default function BlockedDetailState({ signal }: BlockedDetailStateProps) {
  const progress = signal.progress;
  const pct = progress ? Math.min((progress.current / progress.required) * 100, 100) : 0;

  const checklist = [
    {
      label: '60+ dias de historial',
      met: progress ? progress.current >= 60 : false,
    },
    {
      label: 'Cobertura continua',
      met: false,
    },
    {
      label: 'Sin gaps criticos',
      met: false,
    },
  ];

  return (
    <div className="space-y-5">
      {/* Progress */}
      {progress && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">
            Progreso hacia desbloqueo
          </h4>
          <div className="flex items-center gap-3">
            <div className="flex-1 h-2 rounded-full bg-ml-bg-elevated overflow-hidden">
              <div
                className="h-full rounded-full bg-[var(--ml-blocked-500)] transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs font-mono text-ml-text-secondary shrink-0">
              {progress.current}/{progress.required} {progress.unit === 'days' ? 'dias' : progress.unit}
            </span>
          </div>
        </div>
      )}

      {/* Checklist */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">
          Requisitos para habilitar
        </h4>
        <ul className="space-y-1.5">
          {checklist.map((item) => (
            <li key={item.label} className="flex items-center gap-2 text-sm">
              {item.met ? (
                <CheckCircle2 size={14} className="text-[#86EFAC] shrink-0" />
              ) : (
                <Circle size={14} className="text-ml-text-muted shrink-0" />
              )}
              <span className={item.met ? 'text-ml-text-secondary' : 'text-ml-text-muted'}>
                {item.label}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Quality notes */}
      {signal.detail?.dataQualityNotes && signal.detail.dataQualityNotes.length > 0 && (
        <div className="space-y-1.5">
          {signal.detail.dataQualityNotes.map((note) => (
            <div
              key={note.code}
              className="flex items-start gap-2 px-3 py-2 rounded-lg bg-ml-bg-elevated border border-ml-border"
            >
              <AlertCircle size={14} className="text-ml-text-muted shrink-0 mt-0.5" />
              <span className="text-xs text-ml-text-muted">{note.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
