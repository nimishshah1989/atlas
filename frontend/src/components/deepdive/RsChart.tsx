"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export type RsPoint = { date: string; rs: number | null };

export default function RsChart({ data }: { data: RsPoint[] }) {
  return (
    <div className="border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">
        Relative Strength vs NIFTY 500 (12m)
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10 }}
            tickFormatter={(v) => v.slice(5)}
          />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            labelFormatter={(v) => `Date: ${v}`}
          />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="rs"
            stroke="#1D9E75"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
