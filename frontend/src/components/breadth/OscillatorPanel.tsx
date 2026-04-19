"use client";

import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import EmptyState from "@/components/ui/EmptyState";

interface BreadthSeriesPoint {
  date: string;
  ema21_count?: number | null;
  dma50_count?: number | null;
  dma200_count?: number | null;
  index_close?: number | null;
  universe_size?: number | null;
  [key: string]: unknown;
}

interface BreadthSeriesData {
  series?: BreadthSeriesPoint[];
  [key: string]: unknown;
}

interface OscillatorPanelProps {
  universe: string;
  indicator: string;
}

const INDICATOR_DATAKEY: Record<string, string> = {
  ema21: "ema21_count",
  dma50: "dma50_count",
  dma200: "dma200_count",
};

const INDICATOR_LABEL: Record<string, string> = {
  ema21: "Above 21-EMA",
  dma50: "Above 50-DMA",
  dma200: "Above 200-DMA",
};

export default function OscillatorPanel({ universe, indicator }: OscillatorPanelProps) {
  const { data, meta, state, error } = useAtlasData<BreadthSeriesData>(
    "/api/v1/stocks/breadth",
    { universe, range: "5y", include: "index_close,events" },
    { dataClass: "eod_breadth" }
  );

  const series = data?.series ?? [];
  const dataKey = INDICATOR_DATAKEY[indicator] ?? "ema21_count";
  const indicatorLabel = INDICATOR_LABEL[indicator] ?? "Breadth";

  return (
    <div data-block="oscillator" data-data-class="eod_breadth">
      <DataBlock
        state={state}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No oscillator data"
        emptyBody="Breadth time series data is not available for this universe."
      >
        {data && series.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={series} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />

                {/* Overbought zone (≥400) */}
                <ReferenceArea
                  yAxisId="left"
                  y1={400}
                  y2={500}
                  fill="var(--rag-red-100, #fee2e2)"
                  fillOpacity={0.5}
                />
                {/* Oversold zone (≤100) */}
                <ReferenceArea
                  yAxisId="left"
                  y1={0}
                  y2={100}
                  fill="var(--rag-green-100, #dcfce7)"
                  fillOpacity={0.5}
                />

                {/* Midline at 250 */}
                <ReferenceLine
                  yAxisId="left"
                  y={250}
                  stroke="#9ca3af"
                  strokeDasharray="4 2"
                  label={{ value: "Mid", fontSize: 10, fill: "#9ca3af" }}
                />

                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10 }}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="left"
                  domain={[0, 500]}
                  tick={{ fontSize: 10 }}
                  label={{ value: "Count", angle: -90, position: "insideLeft", fontSize: 10 }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 10 }}
                  label={{ value: "Index", angle: 90, position: "insideRight", fontSize: 10 }}
                />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any, name: any) => [
                    `${typeof value === "number" ? value.toFixed(0) : "—"}`,
                    String(name ?? ""),
                  ]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />

                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey={dataKey}
                  name={indicatorLabel}
                  fill="#1D9E75"
                  fillOpacity={0.25}
                  stroke="#1D9E75"
                  dot={false}
                  strokeWidth={1.5}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="index_close"
                  name="Index Close"
                  stroke="#2563eb"
                  dot={false}
                  strokeWidth={1.5}
                />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: ATLAS breadth pipeline · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>

      {/* ROC sub-panel — data-v2-derived, Coming soon */}
      <div data-v2-derived="true" className="mt-4">
        <EmptyState title="Coming soon" />
      </div>
    </div>
  );
}
