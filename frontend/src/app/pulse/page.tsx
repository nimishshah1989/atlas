"use client";

import { useEffect } from "react";
import RegimeBanner from "@/components/pulse/RegimeBanner";
import GlanceStrip from "@/components/pulse/GlanceStrip";
import SectorBoard from "@/components/pulse/SectorBoard";
import MoverStrip from "@/components/pulse/MoverStrip";
import FundStrip from "@/components/pulse/FundStrip";
import SignalStrip from "@/components/pulse/SignalStrip";
import DivergencesBlock from "@/components/pulse/DivergencesBlock";
import EventsOverlay from "@/components/pulse/EventsOverlay";
import EmptyState from "@/components/ui/EmptyState";

export default function PulsePage() {
  useEffect(() => {
    document.title = "ATLAS · Pulse";
  }, []);

  return (
    <main style={{ background: "var(--bg-app)", minHeight: "100vh" }}>
      {/* Page header */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)", padding: "var(--space-4) var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto" }}>
          <div className="crumb" style={{ padding: 0, marginBottom: 4 }}>
            <span>Global</span>
            <span className="crumb__sep">›</span>
            <strong style={{ color: "var(--text-primary)" }}>India · Pulse</strong>
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "var(--fs-2xl)", fontWeight: 400, color: "var(--text-primary)", margin: 0, lineHeight: 1.2 }}>
            Market Pulse
          </h1>
          <p style={{ fontSize: "var(--fs-sm)", color: "var(--text-tertiary)", marginTop: 4, marginBottom: 0 }}>
            Regime · Breadth · Sectors · Movers · Divergences
          </p>
        </div>
      </div>

      <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", padding: "0 var(--space-6) var(--space-10)" }}>

        {/* Regime Banner */}
        <div style={{ marginTop: "var(--space-5)" }}>
          <RegimeBanner />
        </div>

        {/* Signal Strip — 3 DMA cards */}
        <div>
          <div className="sec-hd">
            <h3>Breadth Signals</h3>
            <span className="sec-sub">Nifty 500 · DMA participation</span>
          </div>
          <SignalStrip />
        </div>

        {/* At a Glance — dense metric grid */}
        <div>
          <div className="sec-hd">
            <h3>At a Glance</h3>
            <span className="sec-sub">Key breadth metrics · end of day</span>
          </div>
          <GlanceStrip />
        </div>

        {/* Sector Board + Mover Strip — 2 col */}
        <div>
          <div className="sec-hd">
            <h3>Sector Rotation &amp; Top Movers</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <SectorBoard />
            <MoverStrip />
          </div>
        </div>

        {/* Fund Movers */}
        <div>
          <div className="sec-hd">
            <h3>Fund Movers</h3>
            <span className="sec-sub">Top RS funds</span>
          </div>
          <FundStrip />
        </div>

        {/* Divergences + Events — 2 col */}
        <div>
          <div className="sec-hd">
            <h3>Divergences &amp; Events</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <DivergencesBlock />
            <EventsOverlay />
          </div>
        </div>

        {/* Decision Cards — deferred */}
        <div data-v2-deferred="true">
          <div className="sec-hd">
            <h3>Decision Cards</h3>
            <span className="sec-badge">V2</span>
          </div>
          <EmptyState
            title="Coming soon"
            body="AI-powered decision cards will be available in a future release."
          />
        </div>

      </div>
    </main>
  );
}
