"use client";

import React from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";

export interface SparklinePoint {
  date: string;
  nav: number | null;
}

interface SparklineCellProps {
  data: SparklinePoint[] | null | undefined;
}

export default function SparklineCell({ data }: SparklineCellProps) {
  if (!data || data.length === 0) {
    return <span className="text-gray-300 text-xs">—</span>;
  }

  const points = data
    .filter((d) => d.nav !== null)
    .map((d) => ({ v: d.nav as number }));

  if (points.length < 2) {
    return <span className="text-gray-300 text-xs">—</span>;
  }

  const first = points[0].v;
  const last = points[points.length - 1].v;
  const lineColor = last >= first ? "#10b981" : "#ef4444";

  return (
    <div style={{ width: 60, height: 24 }} data-testid="sparkline-cell">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={lineColor}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
