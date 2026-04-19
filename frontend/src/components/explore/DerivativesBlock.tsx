"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal, formatCurrency } from "@/lib/format";

// PCR endpoint returns { data: [{ trade_date, pcr_oi, pcr_volume, total_oi }], _meta }
interface PcrRow {
  trade_date?: string;
  pcr_oi?: string | number | null;
  pcr_volume?: string | number | null;
  total_oi?: number | null;
  [key: string]: unknown;
}

type DerivativesData = PcrRow[];

export default function DerivativesBlock() {
  const { data, meta, state, error } = useAtlasData<DerivativesData>(
    "/api/derivatives/pcr/NIFTY",
    undefined,
    { dataClass: "intraday" }
  );

  // DataBlock renders EmptyState automatically when state === "empty"
  // useAtlasData returns state="empty" when meta.insufficient_data === true
  // So no special handling needed — sparse behavior is automatic.

  return (
    <div data-block="derivatives-block">
      <DataBlock
        state={state}
        dataClass="intraday"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="Derivatives data unavailable"
        emptyBody="F&O bhavcopy data is not yet available for today's session."
      >
        {Array.isArray(data) && data.length > 0 && (() => {
          const latest = data[0] as PcrRow;
          return (
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  NIFTY PCR (OI)
                </p>
                <p className="text-2xl font-bold text-gray-900">
                  {formatDecimal(latest.pcr_oi ?? null, 2)}
                </p>
                <p className="text-xs text-gray-400 mt-1">{latest.trade_date ?? "—"}</p>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  PCR (Volume)
                </p>
                <p className="text-2xl font-bold text-gray-900">
                  {latest.pcr_volume != null ? formatDecimal(latest.pcr_volume, 2) : "—"}
                </p>
              </div>
              <div className="bg-white border border-gray-200 rounded-lg p-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  Total OI
                </p>
                <p className="text-2xl font-bold text-gray-900">
                  {latest.total_oi != null
                    ? (latest.total_oi / 1e7).toFixed(1) + " Cr"
                    : "—"}
                </p>
              </div>
            </div>
          );
        })()}
      </DataBlock>
    </div>
  );
}
