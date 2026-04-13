"use client";

import { useEffect, useState } from "react";
import { getFindings, type FindingSummary } from "@/lib/api";

/** Color classes for each finding_type */
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

/** Friendly label for finding_type */
function findingTypeLabel(ft: string): string {
  return ft
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function FindingChips({ entity }: { entity: string }) {
  const [findings, setFindings] = useState<FindingSummary[]>([]);

  useEffect(() => {
    getFindings({ entity, limit: 10 })
      .then((res) => setFindings(res.findings))
      .catch(() => {
        // Graceful: findings are optional enrichment; suppress errors
        setFindings([]);
      });
  }, [entity]);

  if (findings.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5" data-testid="finding-chips">
      {findings.map((f) => {
        const confidencePct =
          f.confidence != null
            ? ` · ${Math.round(parseFloat(f.confidence) * 100)}%`
            : "";

        return (
          <span
            key={f.id}
            title={f.content}
            className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded border ${findingTypeColor(f.finding_type)}`}
            data-testid="finding-chip"
          >
            <span className="font-medium">{findingTypeLabel(f.finding_type)}</span>
            <span className="opacity-75">
              {f.title}
              {confidencePct}
            </span>
          </span>
        );
      })}
    </div>
  );
}
