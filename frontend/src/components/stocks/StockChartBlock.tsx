"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { formatDate } from "@/lib/format";

interface ChartPoint {
  date?: string;
  close?: number | null;
  rsi14?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  [key: string]: unknown;
}

interface ChartData {
  series?: ChartPoint[];
  records?: ChartPoint[];
  [key: string]: unknown;
}

interface StockChartBlockProps {
  symbol: string;
}

export default function StockChartBlock({ symbol }: StockChartBlockProps) {
  const { data, meta, state, error } = useAtlasData<ChartData>(
    `/api/v1/stocks/${symbol}/chart-data`,
    { range: "5y", overlays: "rsi14,macd" },
    { dataClass: "eod_breadth" }
  );

  const points = data?.series ?? data?.records ?? [];

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 chart-with-events">
      <DataBlock
        state={state}
        dataClass="eod_breadth"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No chart data"
        emptyBody="Price history is not available for this symbol."
      >
        {points.length > 0 && (
          <div className="space-y-4">
            {/* Price Chart */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Price</p>
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={points} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F3" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v: string | number) => {
                      if (!v) return "";
                      const d = new Date(String(v));
                      return isNaN(d.getTime()) ? String(v) : `${d.getMonth() + 1}/${d.getFullYear().toString().slice(2)}`;
                    }}
                    className="chart__axis-x"
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v: number | string) => `₹${Number(v).toLocaleString("en-IN")}`}
                    className="chart__axis-y"
                  />
                  <Tooltip
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    formatter={(value: any, name: any) => [
                      typeof value === "number" ? `₹${value.toLocaleString("en-IN")}` : String(value ?? "—"),
                      String(name ?? ""),
                    ]}
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    labelFormatter={(label: any) => formatDate(String(label))}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="close"
                    name="Close"
                    stroke="#134F5C"
                    dot={false}
                    strokeWidth={2}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* RSI Sub-chart */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">RSI 14</p>
              <ResponsiveContainer width="100%" height={100}>
                <ComposedChart data={points} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F3" />
                  <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(_v: string | number) => ""} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
                  <Tooltip
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    formatter={(value: any, name: any) => [
                      typeof value === "number" ? value.toFixed(1) : String(value ?? "—"),
                      String(name ?? ""),
                    ]}
                  />
                  <ReferenceLine y={70} stroke="#EF4444" strokeDasharray="4 2" strokeWidth={1} />
                  <ReferenceLine y={30} stroke="#22C55E" strokeDasharray="4 2" strokeWidth={1} />
                  <Line type="monotone" dataKey="rsi14" name="RSI 14" stroke="#7C3AED" dot={false} strokeWidth={1.5} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {/* MACD Sub-chart */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">MACD</p>
              <ResponsiveContainer width="100%" height={100}>
                <ComposedChart data={points} margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF0F3" />
                  <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(_v: string | number) => ""} />
                  <YAxis tick={{ fontSize: 9 }} />
                  <Tooltip
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    formatter={(value: any, name: any) => [
                      typeof value === "number" ? value.toFixed(2) : String(value ?? "—"),
                      String(name ?? ""),
                    ]}
                  />
                  <ReferenceLine y={0} stroke="#9CA3AF" strokeWidth={1} />
                  <Bar dataKey="macd_hist" name="MACD Hist" fill="#93C5FD" opacity={0.8} />
                  <Line type="monotone" dataKey="macd" name="MACD" stroke="#2563EB" dot={false} strokeWidth={1.5} />
                  <Line type="monotone" dataKey="macd_signal" name="Signal" stroke="#F59E0B" dot={false} strokeWidth={1.5} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            <div className="chart__source text-xs text-gray-400">
              Source: JIP de_equity_ohlcv · NSE closing prices
              {meta?.data_as_of && ` · as of ${formatDate(meta.data_as_of)}`}
            </div>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
