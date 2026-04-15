"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const SECTOR_COLORS = [
  "#1D9E75",
  "#2563eb",
  "#d97706",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#65a30d",
  "#db2777",
  "#ea580c",
  "#6b7280",
];

export default function SectorChart({
  sectorWeights,
  onSectorClick,
  activeSector,
}: {
  sectorWeights: Record<string, string>;
  onSectorClick: (sector: string | null) => void;
  activeSector: string | null;
}) {
  const data = Object.entries(sectorWeights)
    .map(([name, w]) => ({ name, value: parseFloat(w) * 100 }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value);

  if (data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-gray-400">
        No sector data available
      </div>
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={2}
            dataKey="value"
            onClick={(entry) => {
              const sector = entry?.name as string | undefined;
              onSectorClick(
                sector === activeSector ? null : (sector ?? null)
              );
            }}
          >
            {data.map((entry, index) => (
              <Cell
                key={entry.name}
                fill={SECTOR_COLORS[index % SECTOR_COLORS.length]}
                opacity={
                  activeSector === null || activeSector === entry.name
                    ? 1
                    : 0.3
                }
                cursor="pointer"
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(val) => [
              typeof val === "number" ? `${val.toFixed(1)}%` : `${val}%`,
              "Weight",
            ]}
          />
          <Legend
            formatter={(value) =>
              value.length > 20 ? value.slice(0, 20) + "\u2026" : value
            }
            wrapperStyle={{ fontSize: "10px" }}
          />
        </PieChart>
      </ResponsiveContainer>
      {activeSector && (
        <div className="text-center">
          <button
            onClick={() => onSectorClick(null)}
            className="text-xs text-[#1D9E75] underline hover:no-underline"
          >
            Clear filter: {activeSector}
          </button>
        </div>
      )}
    </div>
  );
}
