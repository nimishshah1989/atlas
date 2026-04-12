"use client";

import { useState } from "react";
import MarketOverview from "@/components/MarketOverview";
import SectorTable from "@/components/SectorTable";
import StockTable from "@/components/StockTable";
import DeepDivePanel from "@/components/DeepDivePanel";
import DecisionPanel from "@/components/DecisionPanel";

type View =
  | { type: "sectors" }
  | { type: "stocks"; sector: string }
  | { type: "deep-dive"; symbol: string; sector: string };

export default function Home() {
  const [view, setView] = useState<View>({ type: "sectors" });

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1
              className="text-xl font-bold tracking-tight cursor-pointer"
              onClick={() => setView({ type: "sectors" })}
            >
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">
                Pro
              </span>
            </h1>
            {/* Breadcrumb */}
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-4">
              <button
                onClick={() => setView({ type: "sectors" })}
                className="hover:text-gray-800"
              >
                Market
              </button>
              {(view.type === "stocks" || view.type === "deep-dive") && (
                <>
                  <span>/</span>
                  <button
                    onClick={() =>
                      setView({ type: "stocks", sector: (view as { sector: string }).sector })
                    }
                    className="hover:text-gray-800"
                  >
                    {(view as { sector: string }).sector}
                  </button>
                </>
              )}
              {view.type === "deep-dive" && (
                <>
                  <span>/</span>
                  <span className="text-gray-800 font-medium">
                    {view.symbol}
                  </span>
                </>
              )}
            </nav>
          </div>
          <div className="text-xs text-gray-400">
            Jhaveri Intelligence Platform
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-[1600px] mx-auto px-4 py-4 space-y-6">
        {/* Market Overview — always visible */}
        <MarketOverview />

        {/* View-dependent content */}
        {view.type === "sectors" && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-3">
              <SectorTable
                onSelectSector={(sector) =>
                  setView({ type: "stocks", sector })
                }
              />
            </div>
            <div className="lg:col-span-1">
              <DecisionPanel />
            </div>
          </div>
        )}

        {view.type === "stocks" && (
          <StockTable
            sector={view.sector}
            onSelectStock={(symbol) =>
              setView({ type: "deep-dive", symbol, sector: view.sector })
            }
            onBack={() => setView({ type: "sectors" })}
          />
        )}

        {view.type === "deep-dive" && (
          <DeepDivePanel
            symbol={view.symbol}
            onBack={() =>
              setView({ type: "stocks", sector: view.sector })
            }
          />
        )}
      </main>
    </div>
  );
}
