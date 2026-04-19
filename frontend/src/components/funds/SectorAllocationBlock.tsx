"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface SectorSlice {
  sector?: string | null;
  name?: string | null;
  weight?: number | null;
  weight_pct?: number | null;
  value?: number | null;
  [key: string]: unknown;
}

interface SectorData {
  sectors?: SectorSlice[];
  records?: SectorSlice[];
  [key: string]: unknown;
}

const SECTOR_COLORS = [
  "#1D9E75",
  "#2563eb",
  "#7c3aed",
  "#dc2626",
  "#f59e0b",
  "#0891b2",
  "#16a34a",
  "#9333ea",
  "#ea580c",
  "#0d9488",
  "#be185d",
  "#ca8a04",
];

interface SectorAllocationBlockProps {
  id: string;
}

export default function SectorAllocationBlock({ id }: SectorAllocationBlockProps) {
  const { data, meta, state, error } = useAtlasData<SectorData>(
    `/api/v1/mf/${id}/sectors`,
    undefined,
    { dataClass: "holdings" }
  );

  const slices: SectorSlice[] = data?.sectors ?? data?.records ?? [];

  // Inline override for zero-row array
  const effectiveState =
    state === "ready" && slices.length === 0 ? "empty" : state;

  // Normalise: pick the numeric value field
  const chartData = slices.map((s) => ({
    name: s.sector ?? s.name ?? "Other",
    value: s.weight_pct ?? s.weight ?? s.value ?? 0,
  }));

  return (
    <div
      data-block="sector-allocation"
      className="bg-white border border-gray-200 rounded-lg p-6 h-full"
    >
      <DataBlock
        state={effectiveState}
        dataClass="holdings"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No sector data"
        emptyBody="Sector allocation data is not available for this fund."
      >
        {chartData.length > 0 && (
          <div>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  innerRadius={45}
                >
                  {chartData.map((_, i) => (
                    <Cell
                      key={i}
                      fill={SECTOR_COLORS[i % SECTOR_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  formatter={(value: any, name: any) => [
                    `${typeof value === "number" ? value.toFixed(1) : "—"}%`,
                    String(name ?? ""),
                  ]}
                  contentStyle={{ fontSize: 11 }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11 }}
                  iconType="circle"
                  iconSize={8}
                />
              </PieChart>
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
