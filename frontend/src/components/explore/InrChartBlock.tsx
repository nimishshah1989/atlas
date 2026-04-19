"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface InrPoint {
  date: string;
  close?: number | null;
  value?: number | null;
  [key: string]: unknown;
}

interface InrData {
  series?: InrPoint[];
  records?: InrPoint[];
  [key: string]: unknown;
}

export default function InrChartBlock() {
  const { data, meta, state, error } = useAtlasData<InrData>(
    "/api/v1/query",
    { entity_type: "timeseries" },
    { dataClass: "daily_regime" }
  );

  // DataBlock renders EmptyState automatically when state === "empty"
  // useAtlasData returns state="empty" when meta.insufficient_data === true
  // Sparse behavior (USDINR=X has only 3 rows) is handled automatically.

  const points = data?.series ?? data?.records ?? [];

  return (
    <div data-block="inr-chart-block">
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="INR data unavailable"
        emptyBody="USD/INR timeseries data is sparse. Check back later."
      >
        {data && points.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  label={{ value: "Date", position: "insideBottomRight", offset: -4, fontSize: 11 }}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  label={{ value: "INR/USD", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any) => [`₹${typeof value === "number" ? value.toFixed(2) : "—"}`, "INR/USD"]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="close"
                  name="INR/USD"
                  stroke="#1D9E75"
                  dot={false}
                  strokeWidth={1.5}
                />
              </LineChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: ATLAS global price feed · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
