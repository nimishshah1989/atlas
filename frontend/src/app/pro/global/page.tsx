"use client";

import { BriefingPanel } from "./BriefingPanel";
import { RegimePanel } from "./RegimePanel";
import { MacroRatiosPanel } from "./MacroRatiosPanel";
import { RSHeatmapPanel } from "./RSHeatmapPanel";
import { PatternsPanel } from "./PatternsPanel";

export default function GlobalPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Sticky header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/" className="text-xl font-bold tracking-tight">
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">Pro</span>
            </a>
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-2">
              <a href="/" className="hover:text-gray-800">
                Home
              </a>
              <span>/</span>
              <span className="text-gray-800 font-medium">Global</span>
            </nav>
          </div>
          <div className="text-xs text-gray-400">
            Jhaveri Intelligence Platform
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 py-6 space-y-6">
        {/* Page title */}
        <div>
          <h1 className="text-lg font-semibold text-gray-900">
            Global Intelligence Dashboard
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Real-time global market briefing, macro ratios, regime, RS heatmap
            and inter-market patterns. Each panel is independent — one failure
            does not affect others.
          </p>
        </div>

        {/* Row 1: Briefing — full width */}
        <BriefingPanel />

        {/* Row 2: Regime (left) + Macro Ratios (right) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RegimePanel />
          <MacroRatiosPanel />
        </div>

        {/* Row 3: RS Heatmap — full width */}
        <RSHeatmapPanel />

        {/* Row 4: Patterns — full width */}
        <PatternsPanel />
      </main>
    </div>
  );
}
