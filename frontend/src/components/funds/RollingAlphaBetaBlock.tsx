"use client";

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

interface RollingPoint {
  date: string;
  rolling_alpha?: number | null;
  rolling_beta?: number | null;
  [key: string]: unknown;
}

interface RollingData {
  series?: RollingPoint[];
  records?: RollingPoint[];
  rolling_alpha_beta?: RollingPoint[];
  [key: string]: unknown;
}

interface RollingAlphaBetaBlockProps {
  id: string;
}

export default function RollingAlphaBetaBlock({ id }: RollingAlphaBetaBlockProps) {
  const { data, meta, state, error } = useAtlasData<RollingData>(
    `/api/v1/mf/${id}`,
    { include: "rolling_alpha_beta", range: "5y" },
    { dataClass: "daily_regime" }
  );

  const points =
    data?.rolling_alpha_beta ?? data?.series ?? data?.records ?? [];

  return (
    <div
      data-block="rolling-alpha-beta"
      className="bg-white border border-gray-200 rounded-lg p-6"
    >
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No rolling data"
        emptyBody="Rolling alpha and beta data is not available for this fund."
      >
        {points.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={280}>
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
                    `${typeof value === "number" ? value.toFixed(3) : "—"}`,
                    String(name ?? ""),
                  ]}
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke="#6b7280" strokeDasharray="4 2" />
                <Line
                  type="monotone"
                  dataKey="rolling_alpha"
                  name="Rolling Alpha"
                  stroke="#1D9E75"
                  dot={false}
                  strokeWidth={1.5}
                />
                <Line
                  type="monotone"
                  dataKey="rolling_beta"
                  name="Rolling Beta"
                  stroke="#2563eb"
                  dot={false}
                  strokeWidth={1.5}
                />
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
