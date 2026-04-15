"use client";

import { useState } from "react";
import {
  searchIntelligence,
  type FindingSummary,
} from "@/lib/api-intelligence";

// --- Helpers for finding type display ---

function findingTypeColor(ft: string): string {
  switch (ft) {
    case "rs_analysis":
      return "bg-teal-50 text-teal-700 border-teal-200";
    case "technical_analysis":
    case "technical":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "breadth_analysis":
    case "breadth":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "sector_analysis":
    case "sector":
      return "bg-purple-50 text-purple-700 border-purple-200";
    case "rotation":
      return "bg-orange-50 text-orange-700 border-orange-200";
    case "regime":
      return "bg-gray-50 text-gray-700 border-gray-200";
    default:
      return "bg-gray-50 text-gray-600 border-gray-200";
  }
}

function findingTypeLabel(ft: string): string {
  return ft
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatIst(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

// --- FindingCard ---

function FindingCard({ f }: { f: FindingSummary }) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const confidencePct =
    f.confidence != null
      ? `${Math.round(parseFloat(f.confidence) * 100)}%`
      : null;

  const hasEvidence =
    f.evidence != null && Object.keys(f.evidence).length > 0;

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 hover:border-[#1D9E75] transition-colors">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="font-semibold text-gray-900 text-sm leading-snug">
          {f.title}
        </h3>
        {confidencePct != null && (
          <span className="shrink-0 text-xs font-semibold text-[#1D9E75] bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
            {confidencePct}
          </span>
        )}
      </div>

      {/* Content */}
      <p className="text-sm text-gray-600 mb-3 leading-relaxed">{f.content}</p>

      {/* Chips row */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        {/* Finding type chip */}
        <span
          className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-medium ${findingTypeColor(f.finding_type)}`}
        >
          {findingTypeLabel(f.finding_type)}
        </span>

        {/* Entity tag */}
        {f.entity != null && (
          <span className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-slate-50 text-slate-700 border-slate-200 font-mono">
            {f.entity}
          </span>
        )}

        {/* Tag badges */}
        {f.tags != null &&
          f.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-gray-50 text-gray-500 border-gray-200"
            >
              {tag}
            </span>
          ))}
      </div>

      {/* Agent + timestamp footer */}
      <div className="flex items-center justify-between text-xs text-gray-400 border-t border-[#e4e4e8] pt-2 mt-2">
        <span>
          <span className="font-medium text-gray-600">{f.agent_id}</span>
          <span className="mx-1">·</span>
          <span className="italic">{f.agent_type}</span>
        </span>
        <span>{formatIst(f.created_at)}</span>
      </div>

      {/* Evidence collapsible */}
      {hasEvidence && (
        <div className="mt-3">
          <button
            onClick={() => setEvidenceOpen((v) => !v)}
            className="text-xs text-[#1D9E75] hover:underline focus:outline-none"
          >
            {evidenceOpen ? "Hide evidence" : "Show evidence"}
          </button>
          {evidenceOpen && (
            <pre className="mt-2 text-xs bg-gray-50 border border-[#e4e4e8] rounded p-3 overflow-x-auto text-gray-700 whitespace-pre-wrap break-all">
              {JSON.stringify(f.evidence, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// --- Skeleton ---

function SkeletonCard() {
  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 animate-pulse">
      <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
      <div className="h-3 bg-gray-100 rounded w-full mb-1" />
      <div className="h-3 bg-gray-100 rounded w-5/6 mb-3" />
      <div className="flex gap-2 mb-3">
        <div className="h-5 bg-gray-100 rounded w-20" />
        <div className="h-5 bg-gray-100 rounded w-16" />
      </div>
      <div className="h-3 bg-gray-100 rounded w-1/2" />
    </div>
  );
}

// --- Main page ---

const FINDING_TYPES = [
  { value: "", label: "All types" },
  { value: "rs_analysis", label: "RS Analysis" },
  { value: "technical_analysis", label: "Technical" },
  { value: "breadth_analysis", label: "Breadth" },
  { value: "sector_analysis", label: "Sector" },
  { value: "rotation", label: "Rotation" },
  { value: "regime", label: "Regime" },
];

const ENTITY_TYPES = [
  { value: "", label: "All entity types" },
  { value: "equity", label: "Equity" },
  { value: "mf", label: "Mutual Fund" },
  { value: "index", label: "Index" },
  { value: "sector", label: "Sector" },
];

export default function IntelligencePage() {
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState("");
  const [findingType, setFindingType] = useState("");
  const [minConfidence, setMinConfidence] = useState("");
  const [topK, setTopK] = useState("10");

  const [findings, setFindings] = useState<FindingSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function runSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const resp = await searchIntelligence({
        q: query.trim(),
        entity_type: entityType || undefined,
        finding_type: findingType || undefined,
        min_confidence: minConfidence || undefined,
        top_k: topK ? parseInt(topK, 10) : undefined,
      });
      // Prefer the standard envelope `data` key; fall back to `findings`
      setFindings(resp.data ?? resp.findings ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      runSearch();
    }
  }

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
              <span className="text-gray-800 font-medium">Intelligence</span>
            </nav>
          </div>
          <div className="text-xs text-gray-400">
            Jhaveri Intelligence Platform
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 py-6">
        {/* Page title */}
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900">
            Intelligence Explorer
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Semantic search over agent-generated market intelligence findings.
          </p>
        </div>

        {/* Search bar */}
        <div className="flex gap-2 mb-6">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. momentum signals turning positive, sector rotation, breadth divergence..."
            className="flex-1 border border-[#e4e4e8] rounded px-3 py-2 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
            data-testid="search-input"
          />
          <button
            onClick={runSearch}
            disabled={loading || !query.trim()}
            className="bg-[#1D9E75] text-white text-sm font-medium px-5 py-2 rounded hover:bg-[#178a63] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            data-testid="search-button"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: results */}
          <div className="lg:col-span-2 space-y-4">
            {loading && (
              <div className="space-y-4" data-testid="loading-skeleton">
                {[1, 2, 3].map((i) => (
                  <SkeletonCard key={i} />
                ))}
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
                {error}
                <button
                  onClick={runSearch}
                  className="ml-3 text-red-600 underline hover:no-underline"
                >
                  Retry
                </button>
              </div>
            )}

            {!loading && !error && searched && findings != null && findings.length === 0 && (
              <div
                className="bg-gray-50 border border-[#e4e4e8] rounded-lg p-8 text-center text-sm text-gray-500"
                data-testid="empty-state"
              >
                No findings match your search criteria.
              </div>
            )}

            {!loading && !error && findings != null && findings.length > 0 && (
              <div className="space-y-4" data-testid="findings-list">
                <div className="text-xs text-gray-400">
                  {findings.length} finding{findings.length !== 1 ? "s" : ""} returned
                </div>
                {findings.map((f) => (
                  <FindingCard key={f.id} f={f} />
                ))}
              </div>
            )}

            {!loading && !searched && (
              <div className="bg-gray-50 border border-[#e4e4e8] rounded-lg p-8 text-center text-sm text-gray-400">
                Enter a query above to search intelligence findings.
              </div>
            )}
          </div>

          {/* Right: filter sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-white border border-[#e4e4e8] rounded-lg p-5 sticky top-20">
              <h3 className="font-semibold text-gray-900 mb-4 text-sm">
                Filters
              </h3>

              <div className="space-y-4">
                {/* Entity type */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Entity Type
                  </label>
                  <select
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                    className="w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
                  >
                    {ENTITY_TYPES.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Finding type */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Finding Type
                  </label>
                  <select
                    value={findingType}
                    onChange={(e) => setFindingType(e.target.value)}
                    className="w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
                  >
                    {FINDING_TYPES.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Min confidence */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Min Confidence (0–1)
                  </label>
                  <input
                    type="number"
                    value={minConfidence}
                    onChange={(e) => setMinConfidence(e.target.value)}
                    placeholder="e.g. 0.7"
                    min="0"
                    max="1"
                    step="0.05"
                    className="w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
                  />
                </div>

                {/* Top K */}
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Max Results (top_k)
                  </label>
                  <input
                    type="number"
                    value={topK}
                    onChange={(e) => setTopK(e.target.value)}
                    placeholder="10"
                    min="1"
                    max="100"
                    className="w-full border border-[#e4e4e8] rounded px-2 py-1.5 text-sm focus:outline-none focus:border-[#1D9E75] bg-white"
                  />
                </div>

                <button
                  onClick={runSearch}
                  disabled={loading || !query.trim()}
                  className="w-full bg-[#1D9E75] text-white text-sm font-medium py-2 rounded hover:bg-[#178a63] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Apply Filters
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
