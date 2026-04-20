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

interface YieldCurvePoint {
  date: string;
  y2?: number | null;
  y10?: number | null;
  y30?: number | null;
  real?: number | null;
  [key: string]: unknown;
}

interface YieldCurveData {
  series?: YieldCurvePoint[];
  records?: YieldCurvePoint[];
  [key: string]: unknown;
}

export default function YieldCurveBlock() {
  const { data, meta, state, error } = useAtlasData<YieldCurveData>(
    "/api/macros/yield-curve",
    { tenors: "2Y,10Y,30Y,real" },
    { dataClass: "daily_regime" }
  );

  const points = data?.series ?? data?.records ?? [];
  // 503 = no data in de_gsec_yield — treat as empty, not an error banner
  const effectiveState = state === "error" ? "empty" : state;

  return (
    <div data-block="yield-curve-block">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No yield curve data"
        emptyBody="G-Sec yield curve data is not available for this period."
      >
        {data && points.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  label={{ value: "Date", position: "insideBottomRight", offset: -4, fontSize: 11 }}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  label={{ value: "Yield (%)", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any, name: any) => [
                    `${typeof value === "number" ? value.toFixed(2) : "—"}%`,
                    String(name ?? ""),
                  ]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="y2" name="2Y" stroke="#1D9E75" dot={false} strokeWidth={1.5} />
                <Line type="monotone" dataKey="y10" name="10Y" stroke="#2563eb" dot={false} strokeWidth={1.5} />
                <Line type="monotone" dataKey="y30" name="30Y" stroke="#7c3aed" dot={false} strokeWidth={1.5} />
                <Line type="monotone" dataKey="real" name="Real" stroke="#dc2626" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: ATLAS macro pipeline · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
