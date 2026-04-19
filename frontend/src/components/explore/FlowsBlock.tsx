"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatCurrency } from "@/lib/format";

interface FlowPoint {
  date: string;
  fii?: number | null;
  dii?: number | null;
  [key: string]: unknown;
}

interface FlowsData {
  series?: FlowPoint[];
  records?: FlowPoint[];
  [key: string]: unknown;
}

export default function FlowsBlock() {
  const { data, meta, state, error } = useAtlasData<FlowsData>(
    "/api/v1/global/flows",
    { scope: "india", range: "5y" },
    { dataClass: "daily_regime" }
  );

  const points = data?.series ?? data?.records ?? [];

  return (
    <div data-block="flows-block">
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No flows data"
        emptyBody="FII/DII flow data is not available for the selected period."
      >
        {data && points.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={points} margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  label={{ value: "Date", position: "insideBottomRight", offset: -4, fontSize: 11 }}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v: number | string) =>
                    formatCurrency(typeof v === "number" ? v : null)
                  }
                  label={{ value: "Flow (₹)", angle: -90, position: "insideLeft", fontSize: 11 }}
                  width={80}
                />
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(v: any, name: any) =>
                    [formatCurrency(typeof v === "number" ? v : null), String(name ?? "")] as [string, string]
                  }
                  labelStyle={{ fontSize: 11 }}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="fii" name="FII" fill="#1D9E75" />
                <Bar dataKey="dii" name="DII" fill="#2563eb" />
              </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: ATLAS flows pipeline · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
