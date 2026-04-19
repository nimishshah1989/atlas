"use client";

import { useEffect } from "react";
import BreadthCompactBlock from "@/components/explore/BreadthCompactBlock";
import DerivativesBlock from "@/components/explore/DerivativesBlock";
import YieldCurveBlock from "@/components/explore/YieldCurveBlock";
import InrChartBlock from "@/components/explore/InrChartBlock";
import FlowsBlock from "@/components/explore/FlowsBlock";
import SectorsRRGBlock from "@/components/explore/SectorsRRGBlock";
import ZoneEventsTable from "@/components/explore/ZoneEventsTable";
import DivergencesCountryBlock from "@/components/explore/DivergencesCountryBlock";
import EmptyState from "@/components/ui/EmptyState";

export default function ExploreCountryPage() {
  useEffect(() => {
    document.title = "ATLAS · Explore India";
  }, []);

  return (
    <main style={{ background: "var(--bg-app)", minHeight: "100vh" }}>

      {/* Page header */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)", padding: "var(--space-4) var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto" }}>
          <div className="crumb" style={{ padding: 0, marginBottom: 4 }}>
            <span>Global</span>
            <span className="crumb__sep">›</span>
            <strong style={{ color: "var(--text-primary)" }}>India</strong>
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "var(--fs-2xl)", fontWeight: 400, color: "var(--text-primary)", margin: 0, lineHeight: 1.2 }}>
            India Market Landscape
          </h1>
          <p style={{ fontSize: "var(--fs-sm)", color: "var(--text-tertiary)", marginTop: 4, marginBottom: 0 }}>
            Regime · Breadth · Derivatives · Macro · Flows · Sector Rotation
          </p>
        </div>
      </div>

      <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", padding: "0 var(--space-6) var(--space-10)" }}>

        {/* Market Breadth */}
        <div>
          <div className="sec-hd">
            <h3>Market Breadth</h3>
            <span className="sec-sub">Nifty 500</span>
          </div>
          <BreadthCompactBlock />
        </div>

        {/* Derivatives */}
        <div>
          <div className="sec-hd">
            <h3>Derivatives (F&amp;O)</h3>
            <span className="sec-sub">NIFTY Put-Call Ratio</span>
          </div>
          <DerivativesBlock />
        </div>

        {/* Yield Curve + INR — 2 col */}
        <div>
          <div className="sec-hd">
            <h3>Fixed Income &amp; Currency</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: "var(--space-3)" }}>
                G-SEC Yield Curve
              </div>
              <YieldCurveBlock />
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: "var(--space-3)" }}>
                USD / INR
              </div>
              <InrChartBlock />
            </div>
          </div>
        </div>

        {/* FII / DII Flows */}
        <div>
          <div className="sec-hd">
            <h3>FII / DII Flows</h3>
            <span className="sec-sub">Net cash flows</span>
          </div>
          <FlowsBlock />
        </div>

        {/* Sectors RRG */}
        <div>
          <div className="sec-hd">
            <h3>Sector Rotation (RRG)</h3>
          </div>
          <SectorsRRGBlock />
        </div>

        {/* Zone Events + Divergences — 2 col */}
        <div>
          <div className="sec-hd"><h3>Zone Events &amp; Divergences</h3></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <ZoneEventsTable />
            <DivergencesCountryBlock />
          </div>
        </div>

        {/* Signal Playback — deferred */}
        <div data-v2-derived="true">
          <div className="sec-hd">
            <h3>Signal Playback</h3>
            <span className="sec-badge">V2</span>
          </div>
          <EmptyState title="Coming soon" body="Signal playback will be available in a future release." />
        </div>

      </div>
    </main>
  );
}
