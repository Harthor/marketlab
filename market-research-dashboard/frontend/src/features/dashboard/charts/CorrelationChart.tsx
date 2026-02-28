// MarketLab Dashboard v2 — CorrelationChart (spec §7.3.2)

import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts';
import type { SignalDetailData } from '@/types/dashboard';

interface CorrelationChartProps {
  detail: SignalDetailData;
}

export default function CorrelationChart({ detail }: CorrelationChartProps) {
  const series = detail.normalizedOverlaySeries;
  if (!series || series.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg bg-ml-bg-elevated border border-ml-border">
        <p className="text-xs text-ml-text-muted italic">Grafico de correlacion: datos insuficientes</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h4 className="text-xs font-semibold text-ml-text-muted uppercase tracking-wide">BTC vs Senal</h4>
      <div className="h-56 md:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#23314C" />
            <XAxis
              dataKey="ts"
              tick={{ fill: '#7D8BA7', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#23314C' }}
            />
            <YAxis
              tick={{ fill: '#7D8BA7', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: '#23314C' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#152033',
                border: '1px solid #314261',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              labelStyle={{ color: '#AAB8CF' }}
            />
            <Legend wrapperStyle={{ fontSize: '11px', color: '#AAB8CF' }} />
            <Line
              type="monotone"
              dataKey="price"
              name="BTC"
              stroke="#E5EEF8"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="signal"
              name="Senal"
              stroke="#22C55E"
              strokeWidth={2}
              dot={false}
              strokeDasharray="4 2"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
