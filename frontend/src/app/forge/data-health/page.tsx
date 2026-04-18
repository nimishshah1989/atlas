/**
 * /forge/data-health — Data Health page (V11-1)
 *
 * Server component: fetches data health at SSR time from
 * GET /api/v1/system/data-health. Displays one card per domain
 * with six dimension badges and a table list.
 */

import { getDataHealth, TableHealth } from "@/lib/api-data-health";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata = { title: "ATLAS · Data Health" };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function groupByDomain(tables: TableHealth[]): Record<string, TableHealth[]> {
  return tables.reduce(
    (acc, t) => {
      (acc[t.domain] = acc[t.domain] || []).push(t);
      return acc;
    },
    {} as Record<string, TableHealth[]>,
  );
}

function domainDimScore(tables: TableHealth[], dimName: string): number | null {
  const scores = tables.flatMap((t) =>
    t.dimensions.filter((d) => d.name === dimName).map((d) => d.score),
  );
  return scores.length > 0 ? Math.min(...scores) : null;
}

const DIMENSIONS = [
  "coverage",
  "freshness",
  "completeness",
  "continuity",
  "integrity",
  "provenance",
];

function scoreColor(score: number | null): string {
  if (score === null) return "bg-gray-100 text-gray-500";
  if (score >= 80) return "bg-green-100 text-green-800";
  if (score >= 60) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}

function formatIst(isoStr: string | null | undefined): string {
  if (!isoStr) return "—";
  try {
    const dt = new Date(isoStr);
    return dt.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return isoStr;
  }
}

// ---------------------------------------------------------------------------
// Domain card
// ---------------------------------------------------------------------------

function DomainCard({
  domain,
  tables,
}: {
  domain: string;
  tables: TableHealth[];
}) {
  const domainPass = tables.every((t) => t.pass);
  const minOverall = Math.min(...tables.map((t) => t.overall_score));

  return (
    <div
      className={`rounded-lg border p-4 ${
        domainPass ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${
              domainPass ? "bg-green-500" : "bg-red-500"
            }`}
          />
          <h2 className="font-semibold text-gray-900 text-sm truncate">
            {domain.replace(/_/g, " ")}
          </h2>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded ${
              domainPass
                ? "bg-green-200 text-green-800"
                : "bg-red-200 text-red-800"
            }`}
          >
            {domainPass ? "PASS" : "FAIL"}
          </span>
          <span className="text-xs text-gray-500 font-mono">
            {minOverall.toFixed(0)}
          </span>
        </div>
      </div>

      {/* 6 dimension badges */}
      <div className="flex flex-wrap gap-1 mb-3">
        {DIMENSIONS.map((dim) => {
          const score = domainDimScore(tables, dim);
          return (
            <span
              key={dim}
              className={`text-xs px-1.5 py-0.5 rounded font-mono ${scoreColor(score)}`}
              title={`${dim}: ${score !== null ? score.toFixed(1) : "—"}`}
            >
              {dim.slice(0, 4)}: {score !== null ? score.toFixed(0) : "—"}
            </span>
          );
        })}
      </div>

      {/* Table list */}
      <div className="space-y-1">
        {tables.slice(0, 5).map((t) => (
          <div key={t.table} className="flex items-center justify-between text-xs">
            <span
              className="font-mono text-gray-600 truncate max-w-[180px]"
              title={t.table}
            >
              {t.table}
            </span>
            <span
              className={`font-bold ml-2 flex-shrink-0 ${
                t.pass ? "text-green-700" : "text-red-700"
              }`}
            >
              {t.error ? "missing" : t.overall_score.toFixed(0)}
            </span>
          </div>
        ))}
        {tables.length > 5 && (
          <p className="text-xs text-gray-400">+{tables.length - 5} more tables</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function DataHealthPage() {
  const health = await getDataHealth();

  if (!health.available) {
    return (
      <div className="min-h-screen bg-gray-50 font-sans">
        <div className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-gray-900 tracking-tight">
                Data Health
              </h1>
              <p className="text-xs text-gray-400 mt-0.5">
                6-dimension rubric across all Atlas data domains
              </p>
            </div>
            <a
              href="/forge"
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              ← Forge Dashboard
            </a>
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-6 py-12 text-center">
          <p className="text-gray-500 text-sm">
            data-health.json not yet generated.
          </p>
          <p className="text-gray-400 text-xs mt-2">
            Run:{" "}
            <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">
              python scripts/check-data-coverage.py
            </code>
          </p>
        </div>
      </div>
    );
  }

  const grouped = groupByDomain(health.tables);
  const domains = Object.keys(grouped).sort();
  const passCount = domains.filter((d) => grouped[d].every((t) => t.pass))
    .length;
  const failCount = domains.length - passCount;

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Top bar matching forge chrome */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">
              Data Health
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">
              6-dimension rubric across all Atlas data domains
            </p>
          </div>
          <div className="flex items-center gap-3">
            <a
              href="/forge"
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              ← Forge Dashboard
            </a>
            <span className="text-xs text-gray-400">
              as of {formatIst(health.generated_at)}
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Summary bar */}
        <div className="flex flex-wrap gap-4 text-sm mb-6">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-gray-400 inline-block" />
            <span className="text-gray-600">
              Total:{" "}
              <span className="font-semibold text-gray-900">
                {domains.length}
              </span>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
            <span className="text-gray-600">
              Passing:{" "}
              <span className="font-semibold text-green-700">{passCount}</span>
            </span>
          </div>
          {failCount > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
              <span className="text-gray-600">
                Failing:{" "}
                <span className="font-semibold text-red-700">{failCount}</span>
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <span>
              {health.tables.length} tables checked
            </span>
          </div>
        </div>

        {/* Domain cards grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {domains.map((domain) => (
            <DomainCard
              key={domain}
              domain={domain}
              tables={grouped[domain]}
            />
          ))}
        </div>

        {domains.length === 0 && (
          <div className="text-center text-gray-400 py-16 text-sm">
            No domain data found.
          </div>
        )}
      </div>
    </div>
  );
}
