"use client";

import { useEffect, useState } from "react";
import { getMfNavHistory, type MFNAVPoint } from "@/lib/api-mf";

interface MFNAVSparklineProps {
  mstarId: string;
}

function SparklineSVG({ points }: { points: MFNAVPoint[] }) {
  if (points.length < 2) return null;

  const values = points.map((p) => parseFloat(p.nav));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const width = 120;
  const height = 36;
  const padX = 2;
  const padY = 3;

  const chartW = width - padX * 2;
  const chartH = height - padY * 2;

  const coords = values.map((v, i) => {
    const x = padX + (i / (values.length - 1)) * chartW;
    const y = padY + (1 - (v - min) / range) * chartH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polyline = coords.join(" ");

  // First and last value for labels
  const firstVal = values[0];
  const lastVal = values[values.length - 1];
  const pctChange = ((lastVal - firstVal) / firstVal) * 100;
  const isPositive = pctChange >= 0;

  return (
    <div className="flex items-center gap-2">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="shrink-0"
        aria-label="NAV trend sparkline"
      >
        <polyline
          points={polyline}
          fill="none"
          stroke="#1D9E75"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      <span
        className={`text-xs font-medium ${isPositive ? "text-emerald-600" : "text-red-500"}`}
      >
        {isPositive ? "+" : ""}
        {pctChange.toFixed(1)}%
      </span>
    </div>
  );
}

export default function MFNAVSparkline({ mstarId }: MFNAVSparklineProps) {
  const [points, setPoints] = useState<MFNAVPoint[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPoints(null);

    getMfNavHistory(mstarId)
      .then((resp) => {
        if (!cancelled) setPoints(resp.points);
      })
      .catch(() => {
        // Graceful degradation: render nothing on error
        if (!cancelled) setPoints([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mstarId]);

  if (loading) {
    return (
      <div className="animate-pulse h-9 w-32 bg-gray-100 rounded" />
    );
  }

  if (!points || points.length < 2) return null;

  return <SparklineSVG points={points} />;
}
