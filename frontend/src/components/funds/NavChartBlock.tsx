"use client";

import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface NavPoint {
  date: string;
  nav?: number | null;
  nav_indexed?: number | null;
  benchmark?: number | null;
  benchmark_tri?: number | null;
  [key: string]: unknown;
}

interface NavEvent {
  date: string;
  label?: string | null;
  [key: string]: unknown;
}

interface NavChartData {
  series?: NavPoint[];
  records?: NavPoint[];
  events?: NavEvent[];
  [key: string]: unknown;
}

const RANGE_OPTIONS = ["1M", "6M", "1Y", "3Y", "5Y", "SI"] as const;
type RangeOption = (typeof RANGE_OPTIONS)[number];

interface NavChartBlockProps {
  id: string;
}

export default function NavChartBlock({ id }: NavChartBlockProps) {
  const [range, setRange] = useState<RangeOption>("5Y");

  const { data, meta, state, error } = useAtlasData<NavChartData>(
    `/api/v1/mf/${id}/nav-history`,
    { range: range.toLowerCase(), include: "benchmark_tri,events" },
    { dataClass: "daily_regime" }
  );

  const points = data?.series ?? data?.records ?? [];
  const events: NavEvent[] = data?.events ?? [];

  return (
    <div
      data-block="nav-chart"
      className="bg-white border border-gray-200 rounded-lg p-6"
    >
      {/* Range selector */}
      <div className="flex gap-1 mb-4">
        {RANGE_OPTIONS.map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
              range === r
                ? "bg-teal-700 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No NAV history"
        emptyBody="NAV history data is not available for this fund."
      >
        {points.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart
                data={points}
                margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v?.slice(0, 7) ?? v}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any, name: any) => [
                    `${typeof value === "number" ? value.toFixed(2) : "—"}`,
                    String(name ?? ""),
                  ]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="nav_indexed"
                  name="Fund NAV"
                  stroke="#1D9E75"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark_tri"
                  name="Benchmark TRI"
                  stroke="#9ca3af"
                  dot={false}
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                />
                {events.map((ev, i) => (
                  <ReferenceLine
                    key={i}
                    x={ev.date}
                    stroke="#f59e0b"
                    strokeDasharray="3 3"
                    label={{
                      value: ev.label ?? "",
                      fontSize: 9,
                      fill: "#b45309",
                    }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: ATLAS MF pipeline · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
