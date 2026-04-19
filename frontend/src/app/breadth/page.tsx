"use client";

import { useEffect, useState } from "react";
import UniverseSelector from "@/components/breadth/UniverseSelector";
import IndicatorSelector from "@/components/breadth/IndicatorSelector";
import HeroKPIRow from "@/components/breadth/HeroKPIRow";
import OscillatorPanel from "@/components/breadth/OscillatorPanel";
import ZoneLabelsBlock from "@/components/breadth/ZoneLabelsBlock";
import SignalHistoryBlock from "@/components/breadth/SignalHistoryBlock";
import DivergencesBlock from "@/components/breadth/DivergencesBlock";
import ConvictionHaloBlock from "@/components/breadth/ConvictionHaloBlock";
import EmptyState from "@/components/ui/EmptyState";

export default function BreadthPage() {
  const [universe, setUniverse] = useState<string>("nifty500");
  const [indicator, setIndicator] = useState<string>("ema21");

  useEffect(() => {
    document.title = "ATLAS · Breadth Terminal";
  }, []);

  return (
    <main style={{ background: "var(--bg-app)", minHeight: "100vh" }}>

      {/* Page header */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-default)", padding: "var(--space-4) var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto" }}>
          <div className="crumb" style={{ padding: 0, marginBottom: 4 }}>
            <a href="/pulse">Pulse</a>
            <span className="crumb__sep">›</span>
            <a href="/explore/country">India</a>
            <span className="crumb__sep">›</span>
            <strong style={{ color: "var(--text-primary)" }}>Breadth Terminal</strong>
          </div>
          <h1 style={{ fontFamily: "var(--font-serif)", fontSize: "var(--fs-2xl)", fontWeight: 400, color: "var(--text-primary)", margin: 0, lineHeight: 1.2 }}>
            Breadth Terminal
          </h1>
          <p style={{ fontSize: "var(--fs-sm)", color: "var(--text-tertiary)", marginTop: 4, marginBottom: 0 }}>
            Market breadth oscillator · zone history · divergence signals
          </p>
        </div>
      </div>

      {/* Selector bar */}
      <div style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border-subtle)", padding: "0 var(--space-6)" }}>
        <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", display: "flex", alignItems: "center", gap: "var(--space-6)", height: 44 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em" }}>Universe</span>
            <UniverseSelector universe={universe} onUniverseChange={setUniverse} />
          </div>
          <div style={{ width: 1, height: 20, background: "var(--border-subtle)" }} />
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em" }}>Indicator</span>
            <IndicatorSelector indicator={indicator} onIndicatorChange={setIndicator} />
          </div>
        </div>
      </div>

      <div style={{ maxWidth: "var(--maxw-page)", margin: "0 auto", padding: "0 var(--space-6) var(--space-10)" }}>

        {/* Hero KPI Row */}
        <div>
          <div className="sec-hd">
            <h3>Current Breadth</h3>
            <span className="sec-sub">{universe.toUpperCase()}</span>
          </div>
          <HeroKPIRow universe={universe} />
        </div>

        {/* Oscillator */}
        <div>
          <div className="sec-hd">
            <h3>Breadth Oscillator</h3>
            <span className="sec-sub">5-year history</span>
          </div>
          <OscillatorPanel universe={universe} indicator={indicator} />
        </div>

        {/* Zone Labels */}
        <div>
          <div className="sec-hd">
            <h3>Zone Reference</h3>
          </div>
          <ZoneLabelsBlock universe={universe} />
        </div>

        {/* Methodology */}
        <div style={{ background: "var(--bg-surface)", border: "var(--border-card)", borderRadius: "var(--radius-md)", padding: "var(--space-4)", marginBottom: "var(--space-4)" }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: "var(--space-2)" }}>Methodology</div>
          <p style={{ fontSize: "var(--fs-xs)", color: "var(--text-secondary)", lineHeight: "var(--lh-loose)", margin: 0 }}>
            Breadth counts the number of stocks in the selected universe trading above the chosen moving average.
            Overbought zone (≥ 400 of 500) signals broad participation — historically associated with strong trend
            continuation but also near-term exhaustion risk. Oversold zone (≤ 100 of 500) signals narrow participation
            — potential capitulation or base-building phase.
          </p>
        </div>

        {/* Signal History */}
        <div>
          <div className="sec-hd">
            <h3>Zone Transition History</h3>
          </div>
          <SignalHistoryBlock universe={universe} />
        </div>

        {/* Divergences + Conviction Halo — 2 col */}
        <div>
          <div className="sec-hd"><h3>Divergences &amp; Conviction</h3></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <DivergencesBlock universe={universe} />
            <ConvictionHaloBlock universe={universe} />
          </div>
        </div>

        {/* Signal Playback — deferred */}
        <div data-v2-derived="true">
          <div className="sec-hd">
            <h3>Signal Playback</h3>
            <span className="sec-badge">V2</span>
          </div>
          <EmptyState title="Coming soon" body="Signal playback simulator will be available in a future release." />
        </div>

      </div>
    </main>
  );
}
