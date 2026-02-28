// MarketLab Dashboard v2 — TimelineNarrative (spec §7.3.4)

import type { SignalCardKey } from '@/types/dashboard';

interface TimelineNarrativeProps {
  cardKey: SignalCardKey;
}

const timelines: Record<SignalCardKey, string[]> = {
  trends: [
    'Hace 2 semanas: subieron busquedas de "bitcoin"',
    'Hoy: BTC mostro movimiento al alza',
  ],
  fng: [
    'Ayer: BTC se movio fuerte',
    'Hoy: cambio el indice de miedo/codicia',
  ],
  rss: [
    'Hace 2 dias: aumento el tono positivo en noticias',
    'Hoy: BTC mostro una respuesta moderada',
  ],
  reddit: [],
  wikipedia: [
    'Hace 3 dias: aumentaron pageviews de "Bitcoin" en Wikipedia',
    'Hoy: BTC mostro correlacion con la atencion publica',
  ],
  onchain: [
    'Ayer: aumento el TVL en DeFi Ethereum',
    'Hoy: metricas on-chain muestran actividad elevada',
  ],
};

export default function TimelineNarrative({ cardKey }: TimelineNarrativeProps) {
  const nodes = timelines[cardKey];
  if (!nodes || nodes.length === 0) return null;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Linea de tiempo</h4>
      <div className="flex items-start gap-0">
        {nodes.map((text, i) => (
          <div key={i} className="flex items-start gap-0 flex-1">
            {/* Node */}
            <div className="flex flex-col items-center shrink-0">
              <div className={`w-3 h-3 rounded-full border-2 ${
                i === 0 ? 'border-[var(--ml-green-500)] bg-[var(--ml-green-soft)]' : 'border-ml-border bg-ml-bg-elevated'
              }`} />
              {i < nodes.length - 1 && (
                <div className="w-0 flex-1 min-h-[2rem]" />
              )}
            </div>
            {/* Connector line */}
            {i < nodes.length - 1 && (
              <div className="flex-1 h-px bg-ml-border mt-1.5 mx-1" />
            )}
            {i === nodes.length - 1 && <div className="flex-1" />}
            {/* Label */}
            <div className="sr-only">{text}</div>
          </div>
        ))}
      </div>
      {/* Labels below */}
      <div className="flex gap-2">
        {nodes.map((text, i) => (
          <p key={i} className="flex-1 text-xs text-ml-text-secondary leading-snug">
            {text}
          </p>
        ))}
      </div>
    </div>
  );
}
