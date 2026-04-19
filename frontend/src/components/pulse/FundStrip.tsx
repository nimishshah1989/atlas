"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDecimal } from "@/lib/format";

interface TopRSFund {
  mstar_id: string;
  fund_name: string;
  rs_composite: number | null;
  category_name: string | null;
  quadrant: string | null;
}

export default function FundStrip() {
  const { data, meta, state, error } = useAtlasData<TopRSFund[]>(
    "/api/v1/mf/top-rs",
    { limit: 5 },
    { dataClass: "holdings" }
  );

  // data is an array (wrapped by apiFetch normalization via top-rs's { data: [...], _meta: {...} })
  const funds: TopRSFund[] = Array.isArray(data) ? data : [];

  return (
    <DataBlock
      state={state}
      dataClass="holdings"
      dataAsOf={meta?.data_as_of ?? null}
      errorCode={error?.code}
      errorMessage={error?.message}
      emptyTitle="No fund data"
      emptyBody="Top fund RS data is unavailable."
    >
      {funds.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-2" data-block="fund-strip">
          {funds.map((fund, i) => (
            <div
              key={fund.mstar_id ?? i}
              className="min-w-48 border border-gray-200 rounded p-3 bg-white flex flex-col gap-1"
            >
              <span
                className="font-semibold text-gray-800 text-sm truncate"
                title={fund.fund_name}
              >
                {fund.fund_name}
              </span>
              <span className="text-xs text-gray-500">
                RS: {formatDecimal(fund.rs_composite !== null ? String(fund.rs_composite) : null)}
              </span>
              {fund.category_name !== null && (
                <span className="text-xs text-gray-400 truncate">
                  {fund.category_name}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </DataBlock>
  );
}
