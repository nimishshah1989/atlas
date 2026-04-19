"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal, formatCurrency } from "@/lib/format";

interface DerivativesData {
  pcr?: number | string | null;
  oi_change?: number | string | null;
  max_pain?: number | string | null;
  iv_percentile?: number | string | null;
  [key: string]: unknown;
}

export default function DerivativesBlock() {
  const { data, meta, state, error } = useAtlasData<DerivativesData>(
    "/api/v1/derivatives/summary",
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
        {data && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Put/Call Ratio
              </p>
              <p className="text-2xl font-bold text-gray-900">
                {formatDecimal(data.pcr ?? null, 2)}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                OI Change
              </p>
              <p className="text-2xl font-bold text-gray-900">
                {formatDecimal(data.oi_change ?? null, 0)}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Max Pain
              </p>
              <p className="text-2xl font-bold text-gray-900">
                {formatCurrency(data.max_pain ?? null)}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                IV Percentile
              </p>
              <p className="text-2xl font-bold text-gray-900">
                {formatDecimal(data.iv_percentile ?? null, 1)}%
              </p>
            </div>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
