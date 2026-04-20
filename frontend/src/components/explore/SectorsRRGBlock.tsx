"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import EmptyState from "@/components/ui/EmptyState";
import { quadrantColor, formatDecimal } from "@/lib/format";

interface SectorRRGPoint {
  symbol?: string;
  name?: string;
  rs?: number | null;
  gold_rs?: number | null;
  momentum?: number | null;
  conviction?: number | null;
  quadrant?: string | null;
  [key: string]: unknown;
}

interface SectorsRRGData {
  series?: SectorRRGPoint[];
  records?: SectorRRGPoint[];
  [key: string]: unknown;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: SectorRRGPoint }>;
}

function RRGTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0].payload;
  const qClass = quadrantColor(d.quadrant ?? null);
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-md text-xs">
      <p className={`font-bold mb-1 ${qClass}`}>{d.symbol ?? d.name ?? "—"}</p>
      <p className="text-gray-600">RS: {formatDecimal(d.rs ?? null, 2)}</p>
      <p className="text-gray-600">Gold RS: {formatDecimal(d.gold_rs ?? null, 2)}</p>
      <p className="text-gray-600">Conviction: {formatDecimal(d.conviction ?? null, 2)}</p>
      {d.quadrant && (
        <p className={`mt-1 font-semibold uppercase ${qClass}`}>{d.quadrant}</p>
      )}
    </div>
  );
}

// Group points by quadrant for separate scatter series
function groupByQuadrant(points: SectorRRGPoint[]) {
  const groups: Record<string, SectorRRGPoint[]> = {
    LEADING: [],
    IMPROVING: [],
    WEAKENING: [],
    LAGGING: [],
    OTHER: [],
  };
  for (const p of points) {
    const q = p.quadrant ?? "OTHER";
    if (q in groups) {
      groups[q].push(p);
    } else {
      groups.OTHER.push(p);
    }
  }
  return groups;
}

const QUADRANT_COLORS: Record<string, string> = {
  LEADING: "#10b981",
  IMPROVING: "#2563eb",
  WEAKENING: "#d97706",
  LAGGING: "#dc2626",
  OTHER: "#6b7280",
};

export default function SectorsRRGBlock() {
  const { data, meta, state, error } = useAtlasData<SectorsRRGData>(
    "/api/v1/sectors/rrg",
    { include: "gold_rs,conviction" },
    { dataClass: "daily_regime" }
  );

  // Backend returns { sectors: [...], mean_rs, stddev_rs, as_of, meta }
  // Each sector: { sector, rs_score (str), rs_momentum (str), quadrant, ... }
  const rawSectors = (data as Record<string, unknown> & { sectors?: SectorRRGPoint[] })?.sectors
    ?? data?.series
    ?? data?.records
    ?? [];
  const points: SectorRRGPoint[] = rawSectors.map((s: SectorRRGPoint & Record<string, unknown>) => ({
    ...s,
    name: (s.name as string | undefined) ?? (s["sector"] as string | undefined) ?? undefined,
    symbol: (s.symbol as string | undefined) ?? (s["sector"] as string | undefined) ?? undefined,
    rs: typeof s.rs === "number"
      ? s.rs
      : s["rs_score"] != null ? parseFloat(String(s["rs_score"])) : null,
    momentum: typeof s.momentum === "number"
      ? s.momentum
      : s["rs_momentum"] != null ? parseFloat(String(s["rs_momentum"])) : null,
    gold_rs: s.gold_rs != null ? parseFloat(String(s.gold_rs)) : null,
    conviction: s.conviction != null ? parseFloat(String(s.conviction)) : null,
  }));
  const effectiveState =
    state === "ready" && points.length === 0 ? "empty" : state;
  const groups = groupByQuadrant(points);

  return (
    <div data-block="sectors-rrg-block">
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No sector RRG data"
        emptyBody="Sector RRG data is not available for the selected period."
      >
        {data && points.length > 0 ? (
          <div>
            <ResponsiveContainer width="100%" height={380}>
              <ScatterChart margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  type="number"
                  dataKey="rs"
                  name="RS"
                  tick={{ fontSize: 11 }}
                  label={{ value: "Relative Strength", position: "insideBottomRight", offset: -4, fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="momentum"
                  name="Momentum"
                  tick={{ fontSize: 11 }}
                  label={{ value: "Momentum", angle: -90, position: "insideLeft", fontSize: 11 }}
                />
                <Tooltip content={<RRGTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {/* Reference lines to create quadrant grid */}
                <ReferenceLine x={100} stroke="#9ca3af" strokeDasharray="4 2" />
                <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 2" />
                {(["LEADING", "IMPROVING", "WEAKENING", "LAGGING", "OTHER"] as const).map(
                  (q) =>
                    groups[q].length > 0 ? (
                      <Scatter
                        key={q}
                        name={q}
                        data={groups[q]}
                        fill={QUADRANT_COLORS[q]}
                      />
                    ) : null
                )}
              </ScatterChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-400 mt-2 text-right">
              Source: ATLAS sector RRG engine · as of {meta?.data_as_of ?? "—"}
            </p>
          </div>
        ) : (
          data && points.length === 0 && (
            <EmptyState
              title="No sector RRG data"
              body="Sector RRG data is not available for the selected period."
            />
          )
        )}
      </DataBlock>
    </div>
  );
}
