"use client";

import { useState, useEffect } from "react";
import { getGlobalPatterns, type PatternFinding } from "@/lib/api-global";
import {
  formatIstDate,
  formatIstDateTime,
  PanelError,
  findingTypeColor,
  findingTypeLabel,
} from "./helpers";

export function PatternsPanel() {
  const [patterns, setPatterns] = useState<PatternFinding[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getGlobalPatterns(undefined, 20);
      setPatterns(resp.data ?? resp.patterns ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load patterns");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const latestDate =
    patterns && patterns.length > 0
      ? patterns.reduce((best, p) => {
          const d = p.data_as_of ?? p.created_at;
          if (!d) return best;
          return !best || d > best ? d : best;
        }, null as string | null)
      : null;

  return (
    <div className="bg-white border border-[#e4e4e8] rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-gray-900 text-sm">Inter-market Patterns</h2>
        {latestDate && (
          <span className="text-xs text-gray-400">Data as of {formatIstDate(latestDate)}</span>
        )}
      </div>

      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white border border-[#e4e4e8] rounded-lg p-4 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
              <div className="h-3 bg-gray-100 rounded w-full mb-1" />
              <div className="h-3 bg-gray-100 rounded w-5/6" />
            </div>
          ))}
        </div>
      )}
      {error && <PanelError message={error} onRetry={load} />}

      {!loading && !error && patterns !== null && patterns.length === 0 && (
        <p className="text-sm text-gray-400 text-center py-6">No pattern findings available.</p>
      )}

      {!loading && !error && patterns !== null && patterns.length > 0 && (
        <div className="space-y-3" data-testid="patterns-list">
          {patterns.map((p) => (
            <div
              key={p.id}
              className="bg-white border border-[#e4e4e8] rounded-lg p-4 hover:border-[#1D9E75] transition-colors"
            >
              <div className="flex items-start justify-between gap-3 mb-2">
                <h3 className="font-semibold text-gray-900 text-sm leading-snug">{p.title}</h3>
                {p.confidence != null && (
                  <span className="shrink-0 text-xs font-semibold text-[#1D9E75] bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                    {Math.round(parseFloat(p.confidence) * 100)}%
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 mb-3 leading-relaxed">{p.content}</p>
              <div className="flex flex-wrap items-center gap-1.5 mb-2">
                <span
                  className={`inline-flex items-center text-xs px-2 py-0.5 rounded border font-medium ${findingTypeColor(p.finding_type)}`}
                >
                  {findingTypeLabel(p.finding_type)}
                </span>
                {p.entity != null && (
                  <span className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-slate-50 text-slate-700 border-slate-200 font-mono">
                    {p.entity}
                  </span>
                )}
                {p.tags != null &&
                  p.tags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center text-xs px-2 py-0.5 rounded border bg-gray-50 text-gray-500 border-gray-200"
                    >
                      {tag}
                    </span>
                  ))}
              </div>
              <div className="flex items-center justify-between text-xs text-gray-400 border-t border-[#e4e4e8] pt-2">
                <span>Data as of {formatIstDate(p.data_as_of)}</span>
                <span>{formatIstDateTime(p.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
