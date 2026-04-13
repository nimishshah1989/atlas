"use client";

import { useEffect, useState } from "react";
import {
  getHeartbeat,
  getRoadmap,
  getQuality,
  getLogsTail,
  type HeartbeatResponse,
  type RoadmapResponse,
  type QualityResponse,
  type LogsTailResponse,
} from "@/lib/systemClient";
import HeartbeatStrip from "./HeartbeatStrip";
import RoadmapTree from "./RoadmapTree";
import QualityScores from "./QualityScores";
import ContextFiles, { type ContextFile } from "./ContextFiles";
import LogTail from "./LogTail";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DashState = {
  heartbeat: HeartbeatResponse | null;
  roadmap: RoadmapResponse | null;
  quality: QualityResponse | null;
  log: LogsTailResponse | null;
  context: ContextFile[];
  lastUpdated: string | null;
  error: string | null;
};

// ---------------------------------------------------------------------------
// ForgeDashboard
// ---------------------------------------------------------------------------

export default function ForgeDashboard({
  initial,
}: {
  initial?: Partial<DashState>;
}) {
  const [state, setState] = useState<DashState>({
    heartbeat: initial?.heartbeat ?? null,
    roadmap: initial?.roadmap ?? null,
    quality: initial?.quality ?? null,
    log: initial?.log ?? null,
    context: initial?.context ?? [],
    lastUpdated: null,
    error: null,
  });

  // Fetch all four endpoints in parallel on mount
  useEffect(() => {
    let alive = true;

    const loadAll = async () => {
      try {
        const [hb, rm, ql, lg] = await Promise.allSettled([
          getHeartbeat(),
          getRoadmap(),
          getQuality(),
          getLogsTail(200),
        ]);

        if (!alive) return;

        setState((prev) => ({
          ...prev,
          heartbeat: hb.status === "fulfilled" ? hb.value : prev.heartbeat,
          roadmap: rm.status === "fulfilled" ? rm.value : prev.roadmap,
          quality: ql.status === "fulfilled" ? ql.value : prev.quality,
          log: lg.status === "fulfilled" ? lg.value : prev.log,
          lastUpdated: new Date().toLocaleString("en-IN", {
            timeZone: "Asia/Kolkata",
          }),
          error: null,
        }));
      } catch (e) {
        if (!alive) return;
        setState((prev) => ({
          ...prev,
          error: e instanceof Error ? e.message : "load failed",
        }));
      }
    };

    // Fast refresh for heartbeat + logs every 30s
    const pollHeartbeatLogs = async () => {
      try {
        const [hb, lg] = await Promise.allSettled([
          getHeartbeat(),
          getLogsTail(200),
        ]);
        if (!alive) return;
        setState((prev) => ({
          ...prev,
          heartbeat: hb.status === "fulfilled" ? hb.value : prev.heartbeat,
          log: lg.status === "fulfilled" ? lg.value : prev.log,
        }));
      } catch {
        // keep stale
      }
    };

    loadAll();
    const pollId = setInterval(pollHeartbeatLogs, 30_000);

    return () => {
      alive = false;
      clearInterval(pollId);
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#f9f9f7] text-gray-900">
      {/* Heartbeat strip — sticky top */}
      <HeartbeatStrip initial={state.heartbeat} />

      <div className="max-w-[1400px] mx-auto p-6 space-y-5">
        <header className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              <span className="text-[#1D9E75]">ATLAS</span>
              <span className="text-gray-500 font-normal ml-2 text-base">
                Forge Build Dashboard
              </span>
            </h1>
            <p className="text-xs text-gray-500 mt-1 font-mono">
              {state.lastUpdated
                ? `last loaded ${state.lastUpdated} · heartbeat polls every 30s`
                : "loading…"}
            </p>
          </div>
          {state.error && (
            <span className="text-xs text-red-600 font-mono">{state.error}</span>
          )}
        </header>

        {/* Primary panel: Roadmap tree */}
        <section>
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-3">
            Product Roadmap — V1 → V10
          </h2>
          <RoadmapTree roadmap={state.roadmap} />
        </section>

        {/* Quality scores */}
        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-3">
            Quality Scores
          </h2>
          <QualityScores quality={state.quality} />
        </section>

        {/* Context files — collapsed by default */}
        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <ContextFiles files={state.context} />
        </section>

        {/* Log tail */}
        <section className="bg-white border border-gray-200 rounded-lg p-4">
          <h2 className="text-xs font-mono uppercase tracking-wider text-gray-500 mb-3">
            Latest Orchestrator Log
          </h2>
          <LogTail log={state.log} />
        </section>
      </div>
    </div>
  );
}
