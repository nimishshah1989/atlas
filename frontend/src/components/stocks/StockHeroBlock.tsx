"use client";

import { useEffect } from "react";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatCurrency, formatPercent, formatDate } from "@/lib/format";

interface HeroData {
  symbol?: string;
  name?: string;
  price?: number | string | null;
  change?: number | string | null;
  change_pct?: number | string | null;
  rs_composite?: number | string | null;
  gold_rs?: number | string | null;
  conviction?: number | string | null;
  conviction_band?: string | null;
  sector?: string | null;
  _meta?: { sector?: string | null };
  [key: string]: unknown;
}

interface StockHeroBlockProps {
  symbol: string;
  onSectorLoaded: (sector: string) => void;
}

export default function StockHeroBlock({ symbol, onSectorLoaded }: StockHeroBlockProps) {
  const { data, meta, state, error } = useAtlasData<HeroData>(
    `/api/v1/stocks/${symbol}`,
    { include: "price,chips,rs,gold_rs,conviction" },
    { dataClass: "intraday" }
  );

  useEffect(() => {
    if ((state === "ready" || state === "stale") && data) {
      const sector = (data.sector ?? (data._meta as Record<string, unknown>)?.sector ?? null) as string | null;
      if (sector) onSectorLoaded(sector);
    }
  }, [state, data, onSectorLoaded]);

  const price = formatCurrency(data?.price ?? null);
  const changePct = formatPercent(data?.change_pct ?? null);
  const rs = data?.rs_composite != null ? Number(data.rs_composite).toFixed(1) : "—";
  const goldRs = data?.gold_rs != null ? Number(data.gold_rs).toFixed(1) : "—";
  const conviction = data?.conviction != null ? Number(data.conviction).toFixed(0) : "—";
  const convictionBand = data?.conviction_band ?? null;

  return (
    <div
      data-block="hero"
      data-data-class="intraday"
      className="bg-white border border-gray-200 rounded-lg p-6"
    >
      <DataBlock
        state={state}
        dataClass="intraday"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No data"
        emptyBody="Stock data is not available."
      >
        {data && (
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-2xl font-bold text-gray-900">{data.name ?? symbol}</h1>
                <code className="text-xs px-1.5 py-0.5 bg-gray-100 rounded font-mono text-gray-600">
                  {data.symbol ?? symbol}
                </code>
                {data.sector && (
                  <span className="text-xs px-2 py-0.5 bg-teal-50 border border-teal-200 rounded text-teal-700 font-medium">
                    {String(data.sector)}
                  </span>
                )}
              </div>
              <div className="flex items-baseline gap-4">
                <span className="text-4xl font-bold text-gray-900 tabular-nums">{price}</span>
                <span className={`text-base font-medium ${data?.change_pct != null && Number(data.change_pct) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {changePct}
                </span>
                {meta?.data_as_of && (
                  <span className="text-xs text-gray-400">as of {formatDate(meta.data_as_of)}</span>
                )}
              </div>
            </div>
            <div className="flex gap-3 items-start pt-1">
              <div className="text-center">
                <div className="text-xs text-gray-500 mb-1">RS Composite</div>
                <div className="text-lg font-bold text-gray-900 tabular-nums">{rs}</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500 mb-1">Gold RS</div>
                <div className="text-lg font-bold text-gray-900 tabular-nums">{goldRs}</div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500 mb-1">Conviction</div>
                <div className={`text-lg font-bold tabular-nums ${convictionBand === "high" ? "text-emerald-600" : convictionBand === "low" ? "text-red-600" : "text-amber-600"}`}>
                  {conviction}
                </div>
              </div>
            </div>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
