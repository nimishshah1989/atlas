"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface FxRow {
  rate_date: string;
  currency_pair: string;
  reference_rate: string | number | null;
  source?: string;
  [key: string]: unknown;
}

// /api/macros/fx returns { data: FxRow[], _meta: {...} }
type FxData = FxRow[];

export default function InrChartBlock() {
  const { data, meta, state, error } = useAtlasData<FxData>(
    "/api/macros/fx",
    undefined,
    { dataClass: "daily_regime" }
  );

  // Filter USD/INR rows and sort by date ascending
  const points =
    Array.isArray(data)
      ? [...data]
          .filter((r) => r.currency_pair === "USD/INR" && r.reference_rate != null)
          .sort((a, b) => String(a.rate_date).localeCompare(String(b.rate_date)))
          .map((r) => ({
            date: String(r.rate_date),
            rate: parseFloat(String(r.reference_rate)),
          }))
      : [];

  return (
    <div data-block="inr-chart-block">
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="INR data unavailable"
        emptyBody="USD/INR reference rate data is not available."
      >
        {points.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: string) => v.slice(5)} // show MM-DD
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  domain={["auto", "auto"]}
                  tickFormatter={(v: number) => `₹${v.toFixed(1)}`}
                />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any) => [`₹${typeof value === "number" ? value.toFixed(2) : "—"}`, "USD/INR"]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Line
                  type="monotone"
                  dataKey="rate"
                  name="USD/INR"
                  stroke="#1D9E75"
                  dot={false}
                  strokeWidth={1.5}
                />
              </LineChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: RBI reference rate · as of {points[points.length - 1]?.date ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
