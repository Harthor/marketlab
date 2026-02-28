// MarketLab Dashboard v2 — LagProfile (spec §7.4.2)

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, ReferenceLine } from 'recharts';
import type { LagPoint, LeadMetric, DashboardMode } from '@/types/dashboard';

interface LagProfileProps {
  points?: LagPoint[];
  bestLead?: LeadMetric | null;
  mode: DashboardMode;
}

export default function LagProfile({ points, bestLead, mode }: LagProfileProps) {
  if (!points || points.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg bg-ml-bg-elevated border border-ml-border">
        <p className="text-xs text-ml-text-muted italic">Perfil de lag: datos insuficientes</p>
      </div>
    );
  }

  const bestLag = bestLead?.value ?? null;

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">Perfil de lag</h4>
      <div className="h-48 md:h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={points} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#23314C" vertical={false} />
            <XAxis
              dataKey="lag"
              tick={{ fill: '#7D8BA7', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#23314C' }}
              label={mode === 'pro' ? { value: 'Lag / Lead', fill: '#7D8BA7', fontSize: 10, position: 'bottom' } : undefined}
            />
            <YAxis
              tick={{ fill: '#7D8BA7', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#23314C' }}
              label={mode === 'pro' ? { value: 'r', fill: '#7D8BA7', fontSize: 10, angle: -90, position: 'insideLeft' } : undefined}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#152033',
                border: '1px solid #314261',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              formatter={(value: number) => [value.toFixed(3), 'r']}
              labelFormatter={(label) => `Lag: ${label}`}
            />
            <ReferenceLine y={0} stroke="#314261" />
            <Bar dataKey="correlation" radius={[3, 3, 0, 0]}>
              {points.map((entry) => (
                <Cell
                  key={entry.lag}
                  fill={entry.lag === bestLag ? '#22C55E' : '#314261'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
