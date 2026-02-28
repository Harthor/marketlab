// MarketLab Dashboard v2 — RollingCorrelation (spec §7.4.3)

import { useState, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine, ReferenceArea } from 'recharts';
import type { RollingPoint, SignalCardData } from '@/types/dashboard';

interface RollingCorrelationProps {
  points?: RollingPoint[];
  signal: SignalCardData;
}

const windowColors: Record<string, string> = {
  '8w': '#22C55E',
  '12w': '#EAB308',
  '26w': '#F97316',
  '30d': '#22C55E',
  '60d': '#EAB308',
  '90d': '#F97316',
};

export default function RollingCorrelation({ points, signal }: RollingCorrelationProps) {
  const allWindows = useMemo(() => {
    if (!points || points.length === 0) return [];
    return [...new Set(points.map((p) => p.window))];
  }, [points]);

  const defaultWindow = signal.dataFrequency === 'weekly' ? '12w' : '60d';
  const [selectedWindows, setSelectedWindows] = useState<string[]>(
    allWindows.includes(defaultWindow) ? [defaultWindow] : allWindows.slice(0, 1)
  );

  if (!points || points.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg bg-ml-bg-elevated border border-ml-border">
        <p className="text-xs text-ml-text-muted italic">Correlacion rolling: datos insuficientes</p>
      </div>
    );
  }

  // Pivot data by timestamp
  const pivoted = useMemo(() => {
    const map = new Map<string, Record<string, number | string>>();
    for (const p of points) {
      if (!selectedWindows.includes(p.window)) continue;
      if (!map.has(p.ts)) map.set(p.ts, { ts: p.ts });
      map.get(p.ts)![p.window] = p.value;
    }
    return [...map.values()].sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  }, [points, selectedWindows]);

  const toggleWindow = (w: string) => {
    setSelectedWindows((prev) =>
      prev.includes(w) ? prev.filter((x) => x !== w) : [...prev, w]
    );
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Correlacion rolling</h4>
        <div className="flex gap-1">
          {allWindows.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => toggleWindow(w)}
              className={`px-2 py-0.5 text-[10px] font-mono rounded-chip border transition-colors ${
                selectedWindows.includes(w)
                  ? 'border-ml-border-strong bg-ml-bg-elevated text-ml-text-primary'
                  : 'border-transparent text-ml-text-muted hover:text-ml-text-secondary'
              }`}
            >
              {w}
            </button>
          ))}
        </div>
      </div>
      <div className="h-48 md:h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={pivoted} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#23314C" />
            <XAxis dataKey="ts" tick={{ fill: '#7D8BA7', fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#23314C' }} />
            <YAxis tick={{ fill: '#7D8BA7', fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#23314C' }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#152033', border: '1px solid #314261', borderRadius: '8px', fontSize: '12px' }}
            />
            <ReferenceLine y={0} stroke="#314261" />
            <ReferenceArea y1={-0.05} y2={0.05} fill="#314261" fillOpacity={0.15} />
            {selectedWindows.map((w) => (
              <Line
                key={w}
                type="monotone"
                dataKey={w}
                name={w}
                stroke={windowColors[w] ?? '#AAB8CF'}
                strokeWidth={1.5}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
