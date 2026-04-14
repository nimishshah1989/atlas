"use client";

import { useState } from "react";
import MarketOverview from "@/components/MarketOverview";
import SectorTable from "@/components/SectorTable";
import StockTable from "@/components/StockTable";
import DeepDivePanel from "@/components/DeepDivePanel";
import DecisionPanel from "@/components/DecisionPanel";
import MFCategoryTable from "@/components/mf/MFCategoryTable";
import MFUniverseTree from "@/components/mf/MFUniverseTree";
import MFDeepDive from "@/components/mf/MFDeepDive";
import MFFlowsPanel from "@/components/mf/MFFlowsPanel";
import SimulationBuilder from "@/components/simulate/SimulationBuilder";
import SimulationResults from "@/components/simulate/SimulationResults";
import SavedSimulations from "@/components/simulate/SavedSimulations";
import {
  type SimulationRunResponse,
  type SimulationConfig,
} from "@/lib/api-simulate";

type Tab = "equity" | "mf" | "simulate";

type View =
  | { type: "sectors" }
  | { type: "stocks"; sector: string }
  | { type: "deep-dive"; symbol: string; sector: string }
  | { type: "mf-categories" }
  | { type: "mf-funds"; category: string; broadCategory: string }
  | { type: "mf-deep-dive"; mstarId: string; fundName: string; category: string };

export default function Home() {
  const [tab, setTab] = useState<Tab>("equity");
  const [view, setView] = useState<View>({ type: "sectors" });
  const [simResult, setSimResult] = useState<SimulationRunResponse | null>(
    null
  );
  const [simConfig, setSimConfig] = useState<SimulationConfig | null>(null);
  const [simBuilderConfig, setSimBuilderConfig] =
    useState<SimulationConfig | null>(null);
  const [savedRefresh, setSavedRefresh] = useState(0);

  const handleTabSwitch = (t: Tab) => {
    setTab(t);
    if (t === "equity") {
      setView({ type: "sectors" });
    } else if (t === "mf") {
      setView({ type: "mf-categories" });
    }
  };

  const handleSimResult = (
    result: SimulationRunResponse,
    config: SimulationConfig
  ) => {
    setSimResult(result);
    setSimConfig(config);
  };

  const handleLoadSaved = (config: SimulationConfig) => {
    setSimBuilderConfig(config);
    setSimResult(null);
    setSimConfig(null);
  };

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b bg-white sticky top-0 z-10">
        <div className="max-w-[1600px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1
              className="text-xl font-bold tracking-tight cursor-pointer"
              onClick={() =>
                tab === "equity"
                  ? setView({ type: "sectors" })
                  : setView({ type: "mf-categories" })
              }
            >
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-400 text-sm font-normal ml-2">
                Pro
              </span>
            </h1>

            {/* Tab switcher */}
            <div className="flex items-center border rounded-md overflow-hidden ml-2">
              <button
                onClick={() => handleTabSwitch("equity")}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  tab === "equity"
                    ? "bg-[#1D9E75] text-white"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
              >
                Market
              </button>
              <button
                onClick={() => handleTabSwitch("mf")}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  tab === "mf"
                    ? "bg-[#1D9E75] text-white"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
              >
                Mutual Funds
              </button>
              <button
                onClick={() => handleTabSwitch("simulate")}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  tab === "simulate"
                    ? "bg-[#1D9E75] text-white"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                }`}
              >
                Simulate
              </button>
            </div>

            {/* Breadcrumb */}
            <nav className="flex items-center gap-1 text-sm text-gray-500 ml-2">
              {tab === "equity" && (
                <>
                  <button
                    onClick={() => setView({ type: "sectors" })}
                    className="hover:text-gray-800"
                  >
                    Sectors
                  </button>
                  {(view.type === "stocks" || view.type === "deep-dive") && (
                    <>
                      <span>/</span>
                      <button
                        onClick={() =>
                          setView({
                            type: "stocks",
                            sector: (view as { sector: string }).sector,
                          })
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
                </>
              )}

              {tab === "simulate" && (
                <span className="text-gray-800 font-medium">
                  Simulation Lab
                </span>
              )}

              {tab === "mf" && (
                <>
                  <button
                    onClick={() => setView({ type: "mf-categories" })}
                    className="hover:text-gray-800"
                  >
                    Categories
                  </button>
                  {(view.type === "mf-funds" ||
                    view.type === "mf-deep-dive") && (
                    <>
                      <span>/</span>
                      <button
                        onClick={() => {
                          if (
                            view.type === "mf-funds" ||
                            view.type === "mf-deep-dive"
                          ) {
                            setView({
                              type: "mf-funds",
                              category: view.category,
                              broadCategory:
                                view.type === "mf-funds"
                                  ? view.broadCategory
                                  : "",
                            });
                          }
                        }}
                        className="hover:text-gray-800"
                      >
                        {view.type === "mf-funds" || view.type === "mf-deep-dive"
                          ? view.category
                          : ""}
                      </button>
                    </>
                  )}
                  {view.type === "mf-deep-dive" && (
                    <>
                      <span>/</span>
                      <span className="text-gray-800 font-medium truncate max-w-xs">
                        {view.fundName}
                      </span>
                    </>
                  )}
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

        {/* ── Equity views ── */}
        {tab === "equity" && (
          <>
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
          </>
        )}

        {/* ── MF views ── */}
        {tab === "mf" && (
          <>
            {view.type === "mf-categories" && (
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                <div className="lg:col-span-3">
                  <MFCategoryTable
                    onSelectCategory={(category, broadCategory) =>
                      setView({ type: "mf-funds", category, broadCategory })
                    }
                  />
                </div>
                <div className="lg:col-span-1">
                  <MFFlowsPanel />
                </div>
              </div>
            )}

            {view.type === "mf-funds" && (
              <MFUniverseTree
                filterCategory={view.category}
                onSelectFund={(mstarId, fundName) =>
                  setView({
                    type: "mf-deep-dive",
                    mstarId,
                    fundName,
                    category: view.category,
                  })
                }
                onBack={() => setView({ type: "mf-categories" })}
              />
            )}

            {view.type === "mf-deep-dive" && (
              <MFDeepDive
                mstarId={view.mstarId}
                onBack={() =>
                  setView({
                    type: "mf-funds",
                    category: view.category,
                    broadCategory: "",
                  })
                }
              />
            )}
          </>
        )}

        {/* ── Simulation Lab views ── */}
        {tab === "simulate" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1 space-y-6">
              <SimulationBuilder
                onResult={(result, config) => {
                  handleSimResult(result, config);
                  setSavedRefresh((n) => n + 1);
                }}
                initialConfig={simBuilderConfig}
              />
              <SavedSimulations
                onLoad={handleLoadSaved}
                refreshTrigger={savedRefresh}
              />
            </div>
            <div className="lg:col-span-2">
              {simResult && simConfig ? (
                <SimulationResults response={simResult} config={simConfig} />
              ) : (
                <div className="bg-white border border-[#e4e4e8] rounded-lg p-8 text-center text-sm text-[#9a9aad]">
                  Configure a simulation on the left and click Run Simulation to
                  see results here.
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
