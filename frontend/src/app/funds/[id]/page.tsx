"use client";

import { use, useState, useEffect } from "react";
import EmptyState from "@/components/ui/EmptyState";
import FundHeroBlock from "@/components/funds/FundHeroBlock";
import ReturnsBlock from "@/components/funds/ReturnsBlock";
import NavChartBlock from "@/components/funds/NavChartBlock";
import AlphaRiskBlock from "@/components/funds/AlphaRiskBlock";
import RollingAlphaBetaBlock from "@/components/funds/RollingAlphaBetaBlock";
import HoldingsBlock from "@/components/funds/HoldingsBlock";
import WeightedTechnicalsBlock from "@/components/funds/WeightedTechnicalsBlock";
import SectorAllocationBlock from "@/components/funds/SectorAllocationBlock";
import SuitabilityBlock from "@/components/funds/SuitabilityBlock";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function FundDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const [category, setCategory] = useState<string | null>(null);
  const [fundName, setFundName] = useState<string>(id);

  useEffect(() => {
    document.title = `ATLAS · ${fundName}`;
  }, [fundName]);

  return (
    <main style={{ background: "var(--bg-app)", minHeight: "100vh" }}>

      {/* Page header */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)", padding: "var(--space-4) var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto" }}>
          <div className="crumb" style={{ padding: 0, marginBottom: 4 }}>
            <a href="/funds/rank">Funds</a>
            <span className="crumb__sep">›</span>
            {category && <><span>{category}</span><span className="crumb__sep">›</span></>}
            <strong style={{ color: "var(--text-primary)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {fundName !== id ? fundName : id}
            </strong>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", padding: "0 var(--space-6) var(--space-10)" }}>

        {/* Hero */}
        <div style={{ marginTop: "var(--space-5)" }}>
          <FundHeroBlock id={id} onCategoryLoaded={setCategory} onNameLoaded={setFundName} />
        </div>

        {/* Section A: Performance */}
        <div>
          <div className="sec-hd">
            <h3>Performance</h3>
            <span className="sec-sub">Rolling returns vs benchmark</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <ReturnsBlock id={id} />
            <NavChartBlock id={id} />
          </div>
        </div>

        {/* Section B: Alpha Quality */}
        <div>
          <div className="sec-hd">
            <h3>Alpha Quality &amp; Manager Skill</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <AlphaRiskBlock id={id} />
            <RollingAlphaBetaBlock id={id} />
          </div>
        </div>

        {/* Section C: Holdings */}
        <div>
          <div className="sec-hd">
            <h3>Top Holdings</h3>
            <span className="sec-sub">Latest disclosed portfolio</span>
          </div>
          <HoldingsBlock id={id} />
        </div>

        {/* Section D: Sector Allocation + Weighted Technicals */}
        <div>
          <div className="sec-hd">
            <h3>Sector Allocation &amp; Technicals</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <SectorAllocationBlock id={id} />
            <WeightedTechnicalsBlock id={id} />
          </div>
        </div>

        {/* Section E: Suitability */}
        <div>
          <div className="sec-hd">
            <h3>Suitability</h3>
          </div>
          <SuitabilityBlock id={id} />
        </div>

        {/* Deferred */}
        <div data-v2-deferred="true">
          <div className="sec-hd">
            <h3>AI Recommendations</h3>
            <span className="sec-badge">V2</span>
          </div>
          <EmptyState title="Coming soon" body="AI-powered recommendations will be available in a future release." />
        </div>

      </div>
    </main>
  );
}
