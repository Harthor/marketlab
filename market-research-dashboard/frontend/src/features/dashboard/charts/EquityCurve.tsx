// MarketLab Dashboard v2 — EquityCurve (spec §13.3)

import { AreaChart, Area, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts';

interface EquityCurveProps {
  data: Array<{ ts: string; strategy: number; benchmark: number }>;
}

export default function EquityCurve({ data }: EquityCurveProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 rounded-lg bg-ml-bg-elevated border border-ml-border">
        <p className="text-xs text-ml-text-muted italic">Equity curve: sin datos</p>
      </div>
    );
  }

  return (
    <div className="h-56 md:h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <defs>
            <linearGradient id="gradStrategy" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22C55E" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22C55E" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gradBenchmark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#AAB8CF" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#AAB8CF" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#23314C" />
          <XAxis dataKey="ts" tick={{ fill: '#7D8BA7', fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#23314C' }} />
          <YAxis tick={{ fill: '#7D8BA7', fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#23314C' }} />
          <Tooltip
            contentStyle={{ backgroundColor: '#152033', border: '1px solid #314261', borderRadius: '8px', fontSize: '12px' }}
          />
          <Legend wrapperStyle={{ fontSize: '11px', color: '#AAB8CF' }} />
          <Area
            type="monotone"
            dataKey="benchmark"
            name="Benchmark"
            stroke="#AAB8CF"
            strokeWidth={1.5}
            fill="url(#gradBenchmark)"
          />
          <Area
            type="monotone"
            dataKey="strategy"
            name="Strategy"
            stroke="#22C55E"
            strokeWidth={2}
            fill="url(#gradStrategy)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
