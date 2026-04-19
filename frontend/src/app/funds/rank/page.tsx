"use client";

import React, { useState, useEffect } from "react";
import RegimeBannerRank from "@/components/rank/RegimeBannerRank";
import FilterRail from "@/components/rank/FilterRail";
import RankTable from "@/components/rank/RankTable";

export interface RankFilters {
  category: string | null;
  sub_category: string | null;
  amc: string | null;
  period: string | null;
}

export default function MFRankPage() {
  const [filters, setFilters] = useState<RankFilters>({
    category: null,
    sub_category: null,
    amc: null,
    period: null,
  });

  useEffect(() => {
    document.title = "ATLAS · MF Rank";
  }, []);

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Breadcrumb */}
      <nav className="px-6 pt-4" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-xs text-gray-400">
          <li><a href="/" className="text-gray-500 hover:text-teal-700">Today</a></li>
          <li aria-hidden="true" className="text-gray-300">›</li>
          <li><a href="/explore" className="text-gray-500 hover:text-teal-700">Explore</a></li>
          <li aria-hidden="true" className="text-gray-300">›</li>
          <li className="text-gray-900 font-semibold">MF Rank</li>
        </ol>
      </nav>

      <div className="max-w-7xl mx-auto px-6 py-4 space-y-4">
        {/* Page header */}
        <div className="border-b border-gray-200 pb-4">
          <p className="text-xs font-bold uppercase tracking-widest text-gray-400">
            Mutual Funds · 4-Factor Composite Ranking · v1.1
          </p>
          <h1 className="font-serif text-3xl text-gray-900 font-normal mt-1 mb-2">MF Rank</h1>
          <p className="text-sm text-gray-500 max-w-3xl leading-relaxed">
            Cross-sectional ranking of mutual funds within SEBI categories using four independently
            scored factors: <strong className="text-gray-700">Returns, Risk, Resilience, Consistency.</strong>{" "}
            Each factor is z-scored within category, converted to a 0–100 percentile score via Φ
            (normal CDF), then averaged into a composite.
          </p>
        </div>

        {/* Regime banner */}
        <RegimeBannerRank />

        {/* Factor legend */}
        <div className="flex gap-3 flex-wrap">
          {[
            { key: "returns", label: "Returns", desc: "Excess return vs benchmark: 1Y, 3Y, 5Y weighted.", color: "border-t-emerald-500" },
            { key: "risk", label: "Risk", desc: "Volatility, downside deviation, max drawdown. Lower = higher score.", color: "border-t-amber-500" },
            { key: "resilience", label: "Resilience", desc: "Downside capture ratio, worst rolling 6-month return.", color: "border-t-red-500" },
            { key: "consistency", label: "Consistency", desc: "% of rolling 12-month periods beating the benchmark.", color: "border-t-teal-600" },
          ].map((f) => (
            <div key={f.key} className={`bg-white border border-gray-200 border-t-4 ${f.color} rounded-lg p-3 min-w-[160px] flex-1`} data-factor={f.key}>
              <div className="text-xs font-bold uppercase tracking-widest text-gray-400">{f.label}</div>
              <div className="text-xs text-gray-500 mt-1 leading-relaxed">{f.desc}</div>
              <div className="text-xs font-bold text-teal-700 mt-1">Weight: 25%</div>
            </div>
          ))}
        </div>

        {/* Tie-break bar */}
        <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 border border-gray-200 rounded text-xs text-gray-500">
          <span className="font-bold text-gray-700 uppercase tracking-wider text-xs">Tie-break order</span>
          <span className="text-gray-300">→</span>
          {["Consistency", "Risk", "Returns", "Resilience"].map((item, i, arr) => (
            <React.Fragment key={item}>
              <span className="px-2 py-0.5 bg-teal-50 text-teal-700 border border-teal-200 rounded text-xs font-bold">{item}</span>
              {i < arr.length - 1 && <span className="text-gray-300">→</span>}
            </React.Fragment>
          ))}
        </div>

        {/* Main layout: filter rail + rank table */}
        <div className="grid gap-4" style={{ gridTemplateColumns: "240px 1fr" }}>
          <FilterRail filters={filters} onFiltersChange={setFilters} />
          <RankTable filters={filters} />
        </div>
      </div>
    </main>
  );
}
