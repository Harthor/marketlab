// MarketLab Dashboard v2 — GrangerDirection (spec §7.4.5)

import { ArrowRight, ArrowLeftRight } from 'lucide-react';
import type { GrangerMetric } from '@/types/dashboard';

interface GrangerDirectionProps {
  granger?: GrangerMetric | null;
}

const directionConfig = {
  signal_to_price: { label: 'Senal -> Precio', icon: ArrowRight, color: 'text-[#86EFAC]' },
  price_to_signal: { label: 'Precio -> Senal', icon: ArrowRight, color: 'text-[#FDE68A]' },
  bidirectional: { label: 'Senal <-> Precio', icon: ArrowLeftRight, color: 'text-[#FDBA74]' },
  none: { label: 'Sin direccion', icon: null, color: 'text-ml-text-muted' },
  pending: { label: 'Pendiente', icon: null, color: 'text-ml-text-muted' },
} as const;

export default function GrangerDirection({ granger }: GrangerDirectionProps) {
  if (!granger || !granger.available) {
    return (
      <div className="flex items-center gap-2 py-2">
        <span className="text-xs text-ml-text-muted uppercase tracking-wide font-medium">Granger</span>
        <span className="text-xs text-ml-text-muted italic">Pendiente</span>
      </div>
    );
  }

  const config = directionConfig[granger.direction];
  const Icon = config.icon;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Direccion Granger</h4>
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-ml-bg-elevated border border-ml-border">
        {Icon && <Icon size={16} className={config.color} />}
        <span className={`text-sm font-medium ${config.color}`}>{config.label}</span>
        {granger.pValueForward != null && (
          <span className="text-xs font-mono text-ml-text-muted ml-auto">
            p={granger.pValueForward < 0.001 ? '<0.001' : granger.pValueForward.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  );
}
