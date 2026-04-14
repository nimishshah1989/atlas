"use client";

import { useEffect, useState } from "react";
import { getMfFundDeepDive, type MFFundDeepDiveResponse } from "@/lib/api-mf";
import { formatDecimal, formatCurrency, quadrantColor, quadrantBg, signColor } from "@/lib/format";
import { MetricCard, PillarSection } from "./deepdive/MFPillarSection";
import { TopHoldingsTable, WeightedTechnicalsBlock } from "./deepdive/MFHoldingsSectors";
import MFNAVSparkline from "./deepdive/MFNAVSparkline";
import MFOverlapWidget from "./deepdive/MFOverlapWidget";

function SkeletonLoader() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-8 bg-gray-100 rounded w-1/3" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{[...Array(8)].map((_, i) => <div key={i} className="h-20 bg-gray-100 rounded" />)}</div>
      <div className="grid grid-cols-2 gap-4">{[...Array(4)].map((_, i) => <div key={i} className="h-32 bg-gray-100 rounded" />)}</div>
    </div>
  );
}

export default function MFDeepDive({
  mstarId,
  onBack,
}: {
  mstarId: string;
  onBack: () => void;
}) {
  const [dive, setDive] = useState<MFFundDeepDiveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setDive(null);
    setError(null);

    getMfFundDeepDive(mstarId)
      .then((d) => setDive(d))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [mstarId]);

  if (loading) return <SkeletonLoader />;

  if (error) {
    return (
      <div className="border rounded p-4 text-red-600 text-sm">
        <button onClick={onBack} className="text-gray-500 hover:text-gray-800 mr-3">← Back</button>
        Failed to load fund: {error}
      </div>
    );
  }

  if (!dive) return null;

  const { identity, daily, pillars, sector_exposure, top_holdings, weighted_technicals, staleness, data_as_of } = dive;
  const q = pillars.rs_strength.quadrant;

  const fmtReturn = (val: string | null) =>
    val ? `${parseFloat(val) >= 0 ? "+" : ""}${formatDecimal(val)}%` : "—";
  const fmtAlpha = (val: string | null) =>
    val ? `${parseFloat(val) >= 0 ? "+" : ""}${formatDecimal(val)}` : "—";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-800">← Back</button>
            <h2 className="text-xl font-bold text-gray-900">{identity.fund_name}</h2>
            {q && (
              <span className={`text-xs px-2 py-0.5 rounded border ${quadrantBg(q)} ${quadrantColor(q)}`}>{q}</span>
            )}
            {identity.is_index_fund && (
              <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">Index</span>
            )}
            {dive.inactive && (
              <span className="text-xs px-1.5 py-0.5 bg-red-50 text-red-700 border border-red-200 rounded">Inactive</span>
            )}
            {staleness.flag !== "FRESH" && (
              <span className={`text-xs px-1.5 py-0.5 rounded border ${staleness.flag === "EXPIRED" ? "bg-red-50 text-red-700 border-red-200" : "bg-amber-50 text-amber-700 border-amber-200"}`}>
                {staleness.flag}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-0.5">
            {identity.amc_name} · {identity.category_name} · {identity.broad_category}
            {identity.primary_benchmark ? ` · ${identity.primary_benchmark}` : ""}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-2xl font-bold">{formatCurrency(daily.nav)}</div>
          <div className="text-xs text-gray-400 mb-1">NAV {daily.nav_date ?? "—"}</div>
          {/* NAV sparkline loads async after main data */}
          <MFNAVSparkline mstarId={mstarId} />
        </div>
      </div>

      {/* Key metrics grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="AUM" value={daily.aum_cr ? `₹${formatDecimal(parseFloat(daily.aum_cr))} Cr` : "—"} />
        <MetricCard label="Expense Ratio" value={daily.expense_ratio ? `${formatDecimal(daily.expense_ratio)}%` : "—"} />
        <MetricCard label="1Y Return" value={fmtReturn(daily.return_1y)} colorClass={signColor(daily.return_1y)} />
        <MetricCard label="3Y Return" value={fmtReturn(daily.return_3y)} colorClass={signColor(daily.return_3y)} />
        <MetricCard label="RS Composite" value={formatDecimal(pillars.rs_strength.rs_composite)} colorClass={quadrantColor(q)} />
        <MetricCard label="RS Momentum 28d" value={fmtAlpha(pillars.rs_strength.rs_momentum_28d)} colorClass={signColor(pillars.rs_strength.rs_momentum_28d)} />
        <MetricCard label="Manager Alpha" value={fmtAlpha(pillars.performance.manager_alpha)} colorClass={signColor(pillars.performance.manager_alpha)} />
        <MetricCard label="as of" value={data_as_of} sub={`${staleness.age_minutes}m old`} />
      </div>

      {/* Conviction Pillars */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Conviction Pillars</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PillarSection title="Performance" explanation={pillars.performance.explanation} items={[
            { label: "Manager Alpha", value: fmtAlpha(pillars.performance.manager_alpha), colorClass: signColor(pillars.performance.manager_alpha) },
            { label: "Info Ratio", value: formatDecimal(pillars.performance.information_ratio) },
            { label: "Upside Capture", value: pillars.performance.capture_up ? `${formatDecimal(pillars.performance.capture_up)}%` : "—" },
            { label: "Downside Capture", value: pillars.performance.capture_down ? `${formatDecimal(pillars.performance.capture_down)}%` : "—" },
          ]} />
          <PillarSection title="RS Strength" explanation={pillars.rs_strength.explanation} items={[
            { label: "RS Composite", value: formatDecimal(pillars.rs_strength.rs_composite), colorClass: quadrantColor(q) },
            { label: "RS Momentum 28d", value: fmtAlpha(pillars.rs_strength.rs_momentum_28d), colorClass: signColor(pillars.rs_strength.rs_momentum_28d) },
            { label: "Quadrant", value: q ?? "—", colorClass: quadrantColor(q) },
          ]} />
          <PillarSection title="Flows" explanation={pillars.flows.explanation} items={[
            { label: "Net Flow 3m", value: pillars.flows.net_flow_cr_3m ? `₹${formatDecimal(parseFloat(pillars.flows.net_flow_cr_3m))} Cr` : "—", colorClass: signColor(pillars.flows.net_flow_cr_3m) },
            { label: "SIP Flow 3m", value: pillars.flows.sip_flow_cr_3m ? `₹${formatDecimal(parseFloat(pillars.flows.sip_flow_cr_3m))} Cr` : "—" },
            { label: "Folio Growth", value: pillars.flows.folio_growth_pct ? `${fmtReturn(pillars.flows.folio_growth_pct)}` : "—", colorClass: signColor(pillars.flows.folio_growth_pct) },
          ]} />
          <PillarSection title="Holdings Quality" explanation={pillars.holdings_quality.explanation} items={[
            { label: "Holdings Avg RS", value: formatDecimal(pillars.holdings_quality.holdings_avg_rs) },
            { label: "% Above 200DMA", value: pillars.holdings_quality.pct_above_200dma ? `${formatDecimal(pillars.holdings_quality.pct_above_200dma)}%` : "—" },
            { label: "Top 10 Conc.", value: pillars.holdings_quality.concentration_top10_pct ? `${formatDecimal(pillars.holdings_quality.concentration_top10_pct)}%` : "—" },
          ]} />
        </div>
      </div>

      {/* Returns summary */}
      <div className="border rounded-lg p-4">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Returns</h3>
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {([["1M", daily.return_1m], ["3M", daily.return_3m], ["6M", daily.return_6m],
             ["1Y", daily.return_1y], ["3Y", daily.return_3y], ["5Y", daily.return_5y]] as [string, string | null][]).map(
            ([label, val]) => (
              <div key={label} className="text-center">
                <div className="text-xs text-gray-400">{label}</div>
                <div className={`text-sm font-medium mt-0.5 ${signColor(val)}`}>{fmtReturn(val)}</div>
              </div>
            )
          )}
        </div>
      </div>

      {/* Sector Exposure Summary + Top Holdings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Sector Exposure</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Top: {sector_exposure.top_sector ?? "—"}{sector_exposure.top_sector_weight_pct ? ` (${formatDecimal(sector_exposure.top_sector_weight_pct)}%)` : ""} · {sector_exposure.sector_count} sectors
            </p>
          </div>
          <div className="px-4 py-4">
            {sector_exposure.top_sector ? (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-700 font-medium">{sector_exposure.top_sector}</span>
                  {sector_exposure.top_sector_weight_pct && (
                    <span className="text-gray-900 font-semibold">{formatDecimal(sector_exposure.top_sector_weight_pct)}%</span>
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {sector_exposure.sector_count} total sector{sector_exposure.sector_count !== 1 ? "s" : ""} in portfolio
                </div>
              </div>
            ) : (
              <div className="text-sm text-gray-400 text-center py-2">No sector data</div>
            )}
          </div>
        </div>
        <div className="border rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b bg-gray-50">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Top Holdings</h3>
          </div>
          <TopHoldingsTable topHoldings={top_holdings} holdings={[]} />
        </div>
      </div>

      <WeightedTechnicalsBlock wt={weighted_technicals} />

      {/* Overlap Widget */}
      <MFOverlapWidget mstarId={mstarId} />
    </div>
  );
}
