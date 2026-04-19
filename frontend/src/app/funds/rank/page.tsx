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

const FACTORS = [
  {
    key: "returns",
    label: "Returns",
    desc: "Excess return vs benchmark: 1Y, 3Y, 5Y weighted.",
    color: "var(--rag-green-500)",
  },
  {
    key: "risk",
    label: "Risk",
    desc: "Volatility, downside deviation, max drawdown. Lower = higher score.",
    color: "var(--rag-amber-500)",
  },
  {
    key: "resilience",
    label: "Resilience",
    desc: "Downside capture ratio, worst rolling 6-month return.",
    color: "var(--rag-red-500)",
  },
  {
    key: "consistency",
    label: "Consistency",
    desc: "% of rolling 12-month periods beating the benchmark.",
    color: "var(--accent-700)",
  },
];

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
    <main style={{ background: "var(--bg-app)", minHeight: "100vh" }}>

      {/* Page header */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)", padding: "var(--space-4) var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto" }}>
          <div className="crumb" style={{ padding: 0, marginBottom: 4 }}>
            <a href="/pulse">Pulse</a>
            <span className="crumb__sep">›</span>
            <strong style={{ color: "var(--text-primary)" }}>MF Rank</strong>
          </div>
          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".07em", marginBottom: 4 }}>
            Mutual Funds · 4-Factor Composite Ranking · v1.1
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "var(--fs-2xl)", fontWeight: 400, color: "var(--text-primary)", margin: 0, lineHeight: 1.2 }}>
            MF Rank
          </h1>
          <p style={{ fontSize: "var(--fs-sm)", color: "var(--text-tertiary)", marginTop: 6, marginBottom: 0, maxWidth: 680, lineHeight: "var(--lh-loose)" }}>
            Cross-sectional ranking using four independently scored factors: <strong style={{ color: "var(--text-secondary)", fontWeight: 600 }}>Returns, Risk, Resilience, Consistency.</strong>{" "}
            Each factor is z-scored within category, converted to a 0–100 percentile via Φ (normal CDF), then averaged into a composite.
          </p>
        </div>
      </div>

      <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", padding: "0 var(--space-6) var(--space-10)" }}>

        {/* Regime banner */}
        <div style={{ marginTop: "var(--space-5)", marginBottom: "var(--space-5)" }}>
          <RegimeBannerRank />
        </div>

        {/* Factor legend — 4 cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
          {FACTORS.map((f) => (
            <div
              key={f.key}
              data-factor={f.key}
              style={{
                background: "var(--bg-surface)",
                border: "var(--border-card)",
                borderTop: `3px solid ${f.color}`,
                borderRadius: "var(--radius-md)",
                padding: "var(--space-3) var(--space-4)",
              }}
            >
              <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: 4 }}>
                {f.label}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: "var(--lh-loose)" }}>
                {f.desc}
              </div>
              <div style={{ fontSize: 10, fontWeight: 700, color: "var(--accent-700)", marginTop: 6 }}>
                Weight: 25%
              </div>
            </div>
          ))}
        </div>

        {/* Tie-break bar */}
        <div style={{
          display: "flex", alignItems: "center", gap: "var(--space-2)", padding: "8px var(--space-4)",
          background: "var(--bg-inset)", border: "1px solid var(--border-default)", borderRadius: "var(--radius-md)",
          marginBottom: "var(--space-5)", fontSize: 11,
        }}>
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: "var(--text-secondary)" }}>
            Tie-break order
          </span>
          <span style={{ color: "var(--border-strong)" }}>→</span>
          {["Consistency", "Risk", "Returns", "Resilience"].map((item, i, arr) => (
            <React.Fragment key={item}>
              <span style={{
                padding: "2px 9px", background: "var(--accent-100)", color: "var(--accent-700)",
                border: "1px solid var(--accent-300)", borderRadius: "var(--radius-full)",
                fontSize: 11, fontWeight: 700,
              }}>
                {item}
              </span>
              {i < arr.length - 1 && <span style={{ color: "var(--border-strong)" }}>→</span>}
            </React.Fragment>
          ))}
        </div>

        {/* Main layout: filter rail + rank table */}
        <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: "var(--space-5)" }}>
          <FilterRail filters={filters} onFiltersChange={setFilters} />
          <RankTable filters={filters} />
        </div>

      </div>
    </main>
  );
}
