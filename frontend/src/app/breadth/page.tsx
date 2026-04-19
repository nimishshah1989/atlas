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
    document.title = "ATLAS \u00b7 Breadth Terminal";
  }, []);

  return (
    <main className="min-h-screen bg-gray-50">
      {/* Breadcrumbs */}
      <nav className="px-6 pt-4" aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-xs text-gray-400">
          <li>
            <a href="/" className="text-gray-500 font-medium hover:text-teal-700">
              Today
            </a>
          </li>
          <li aria-hidden="true" className="text-gray-300">
            ›
          </li>
          <li className="text-gray-900 font-semibold">Breadth</li>
        </ol>
      </nav>

      {/* Page header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4 mt-2">
        <h1 className="text-xl font-bold text-gray-900">Breadth Terminal</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Market breadth oscillator, zone history, and divergence signals
        </p>
      </header>

      {/* Selector bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Universe
          </span>
          <UniverseSelector universe={universe} onUniverseChange={setUniverse} />
        </div>
        <div className="w-px h-5 bg-gray-200" aria-hidden="true" />
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Indicator
          </span>
          <IndicatorSelector indicator={indicator} onIndicatorChange={setIndicator} />
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Hero KPI Row */}
        <section aria-label="Breadth KPIs">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Current Breadth
          </h2>
          <HeroKPIRow universe={universe} />
        </section>

        {/* Oscillator Panel */}
        <section aria-label="Breadth Oscillator">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Oscillator (5Y)
          </h2>
          <OscillatorPanel universe={universe} indicator={indicator} />
        </section>

        {/* Zone Labels */}
        <section aria-label="Zone Reference">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Zone Reference
          </h2>
          <ZoneLabelsBlock universe={universe} />
        </section>

        {/* Describe — methodology note */}
        <section aria-label="Methodology" className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-600 mb-1 uppercase tracking-wide">
            Methodology
          </h2>
          <p className="text-xs text-gray-500">
            Breadth counts the number of stocks in the selected universe trading above the
            chosen moving average. Overbought zone (≥ 400 of 500) signals broad
            participation — historically associated with strong trend continuation but
            also near-term exhaustion risk. Oversold zone (≤ 100 of 500) signals
            narrow participation — potential capitulation or base-building phase.
          </p>
        </section>

        {/* Signal History */}
        <section aria-label="Signal History">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Zone Transition History
          </h2>
          <SignalHistoryBlock universe={universe} />
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Divergences */}
          <section aria-label="Factor Divergences">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Factor Divergences
            </h2>
            <DivergencesBlock universe={universe} />
          </section>

          {/* Conviction Halo — data-v2-derived */}
          <section aria-label="Conviction Series" data-v2-derived="true">
            <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
              Conviction Halo
            </h2>
            <ConvictionHaloBlock universe={universe} />
          </section>
        </div>

        {/* Signal Playback — data-v2-derived EmptyState */}
        <section aria-label="Signal Playback" data-v2-derived="true">
          <h2 className="text-sm font-semibold text-gray-600 mb-2 uppercase tracking-wide">
            Signal Playback (Compact)
          </h2>
          <EmptyState
            title="Coming soon"
            body="Signal playback will be available in a future release."
          />
        </section>
      </div>
    </main>
  );
}
