"use client";

import { useEffect } from "react";
import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatCurrency, formatIndianNumber, formatDate } from "@/lib/format";

interface HeroData {
  name?: string | null;
  category?: string | null;
  aum?: number | string | null;
  nav?: number | string | null;
  rs_composite?: number | string | null;
  conviction?: number | string | null;
  conviction_band?: string | null;
  tags?: string[] | null;
  chips?: string[] | null;
  [key: string]: unknown;
}

interface FundHeroBlockProps {
  id: string;
  onCategoryLoaded: (cat: string) => void;
  onNameLoaded?: (name: string) => void;
}

export default function FundHeroBlock({
  id,
  onCategoryLoaded,
  onNameLoaded,
}: FundHeroBlockProps) {
  const { data, meta, state, error } = useAtlasData<HeroData>(
    `/api/v1/mf/${id}`,
    { include: "hero,chips,rs,gold_rs,conviction" },
    { dataClass: "daily_regime" }
  );

  useEffect(() => {
    if ((state === "ready" || state === "stale") && data) {
      if (data.category) onCategoryLoaded(String(data.category));
      if (data.name && onNameLoaded) onNameLoaded(String(data.name));
    }
  }, [state, data, onCategoryLoaded, onNameLoaded]);

  const navDisplay = formatCurrency(data?.nav ?? null);
  const aumDisplay =
    data?.aum != null
      ? `₹${formatIndianNumber(Number(data.aum))}`
      : "—";
  const rs =
    data?.rs_composite != null
      ? Number(data.rs_composite).toFixed(1)
      : "—";
  const conviction =
    data?.conviction != null ? Number(data.conviction).toFixed(0) : "—";
  const convictionBand = data?.conviction_band ?? null;

  const tags = data?.tags ?? data?.chips ?? null;

  return (
    <div
      data-block="hero"
      data-data-class="daily_regime"
      className="bg-white border border-gray-200 rounded-lg p-6"
    >
      <DataBlock
        state={state}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No fund data"
        emptyBody="Fund data is not available."
      >
        {data && (
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap mb-2">
                <h1 className="text-2xl font-bold text-gray-900 truncate">
                  {data.name ?? id}
                </h1>
                {data.category && (
                  <span className="text-xs px-2 py-0.5 bg-teal-50 border border-teal-200 rounded text-teal-700 font-medium whitespace-nowrap">
                    {String(data.category)}
                  </span>
                )}
              </div>

              {/* AUM + NAV row */}
              <div className="flex items-baseline gap-6 flex-wrap">
                <div>
                  <span className="text-xs text-gray-500 mr-1">AUM</span>
                  <span className="text-lg font-semibold text-gray-900 tabular-nums">
                    {aumDisplay}
                  </span>
                </div>
                <div>
                  <span className="text-xs text-gray-500 mr-1">NAV</span>
                  <span className="text-lg font-semibold text-gray-900 tabular-nums">
                    {navDisplay}
                  </span>
                </div>
                {meta?.data_as_of && (
                  <span className="text-xs text-gray-400">
                    as of {formatDate(meta.data_as_of)}
                  </span>
                )}
              </div>

              {/* Tags/chips */}
              {tags && tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {tags.map((tag, i) => (
                    <span
                      key={i}
                      className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Score panel */}
            <div className="flex gap-4 items-start pt-1 shrink-0">
              <div className="text-center">
                <div className="text-xs text-gray-500 mb-1">RS Score</div>
                <div className="text-lg font-bold text-gray-900 tabular-nums">
                  {rs}
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-gray-500 mb-1">Conviction</div>
                <div
                  className={`text-lg font-bold tabular-nums ${
                    convictionBand === "high"
                      ? "text-emerald-600"
                      : convictionBand === "low"
                      ? "text-red-600"
                      : "text-amber-600"
                  }`}
                >
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
