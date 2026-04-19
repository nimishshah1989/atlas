"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface SuitabilityData {
  suitability?: string[] | null;
  tags?: string[] | null;
  horizon?: string | null;
  risk_profile?: string | null;
  [key: string]: unknown;
}

interface SuitabilityBlockProps {
  id: string;
}

export default function SuitabilityBlock({ id }: SuitabilityBlockProps) {
  const { data, meta, state, error } = useAtlasData<SuitabilityData>(
    `/api/v1/mf/${id}`,
    { include: "suitability" },
    { dataClass: "daily_regime" }
  );

  // Collect suitability chips from multiple possible fields
  const chips: string[] = [];

  if (data?.suitability && Array.isArray(data.suitability)) {
    chips.push(...data.suitability);
  }
  if (data?.tags && Array.isArray(data.tags)) {
    chips.push(...data.tags);
  }
  if (data?.horizon && !chips.includes(String(data.horizon))) {
    chips.push(String(data.horizon));
  }
  if (data?.risk_profile && !chips.includes(String(data.risk_profile))) {
    chips.push(String(data.risk_profile));
  }

  const effectiveState =
    state === "ready" && chips.length === 0 ? "empty" : state;

  return (
    <div
      data-block="suitability"
      className="bg-white border border-gray-200 rounded-lg p-6"
    >
      <DataBlock
        state={effectiveState}
        dataClass="daily_regime"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No suitability data"
        emptyBody="Suitability information is not available for this fund."
      >
        {chips.length > 0 && (
          <div>
            <div className="flex flex-wrap gap-2">
              {chips.map((chip, i) => (
                <span
                  key={i}
                  className="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-teal-50 border border-teal-200 text-teal-700"
                >
                  {chip}
                </span>
              ))}
            </div>
            {meta?.data_as_of && (
              <p className="text-xs text-gray-400 mt-3">
                as of {meta.data_as_of}
              </p>
            )}
          </div>
        )}
      </DataBlock>
    </div>
  );
}
