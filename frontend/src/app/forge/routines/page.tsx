/**
 * /forge/routines — Routine Visibility page (V11-0)
 *
 * Server component: fetches routine data at SSR time from
 * GET /api/v1/system/routines. Displays one card per JIP data routine
 * declared in jip-source-manifest.yaml with status colour coding.
 */

import { getRoutines, RoutineEntry, RoutinesResponse } from "@/lib/api-routines";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export const metadata = {
  title: "ATLAS · Routine Visibility",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function statusColors(displayStatus: string): {
  bg: string;
  border: string;
  badge: string;
  badgeText: string;
  dot: string;
} {
  switch (displayStatus) {
    case "live":
      return {
        bg: "bg-white",
        border: "border-green-200",
        badge: "bg-green-100 text-green-800",
        badgeText: "LIVE",
        dot: "bg-green-500",
      };
    case "sla_breached":
      return {
        bg: "bg-red-50",
        border: "border-red-200",
        badge: "bg-red-100 text-red-800",
        badgeText: "SLA BREACHED",
        dot: "bg-red-500",
      };
    case "partial":
      return {
        bg: "bg-amber-50",
        border: "border-amber-200",
        badge: "bg-amber-100 text-amber-800",
        badgeText: "PARTIAL",
        dot: "bg-amber-500",
      };
    case "planned":
      return {
        bg: "bg-gray-50",
        border: "border-gray-200",
        badge: "bg-gray-100 text-gray-600",
        badgeText: "PLANNED",
        dot: "bg-gray-400",
      };
    case "missing":
      return {
        bg: "bg-gray-50",
        border: "border-gray-200",
        badge: "bg-gray-200 text-gray-700",
        badgeText: "MISSING",
        dot: "bg-gray-500",
      };
    default:
      return {
        bg: "bg-white",
        border: "border-gray-200",
        badge: "bg-gray-100 text-gray-500",
        badgeText: displayStatus.toUpperCase(),
        dot: "bg-gray-300",
      };
  }
}

// ---------------------------------------------------------------------------
// Routine card
// ---------------------------------------------------------------------------

function RoutineCard({ routine }: { routine: RoutineEntry }) {
  const colors = statusColors(routine.display_status);

  return (
    <div
      className={`rounded-lg border ${colors.border} ${colors.bg} p-4 flex flex-col gap-2 shadow-sm`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${colors.dot}`} />
          <span className="font-mono text-sm font-semibold text-gray-900 truncate">
            {routine.id}
          </span>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <span
            className={`px-2 py-0.5 rounded text-xs font-semibold tracking-wide ${colors.badge}`}
          >
            {colors.badgeText}
          </span>
          {routine.is_new && (
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-700">
              {routine.priority ?? "NEW"}
            </span>
          )}
        </div>
      </div>

      {/* Tables */}
      {routine.tables.length > 0 && (
        <div className="text-xs text-gray-500 font-mono truncate">
          {routine.tables.join(", ")}
        </div>
      )}

      {/* Cadence + schedule */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
        <span>
          <span className="font-medium">Cadence:</span> {routine.cadence}
        </span>
        {routine.schedule && (
          <span>
            <span className="font-medium">Schedule:</span>{" "}
            <span className="font-mono">{routine.schedule}</span>
          </span>
        )}
        {routine.sla_freshness_hours !== null && routine.sla_freshness_hours !== undefined && (
          <span>
            <span className="font-medium">SLA:</span> {routine.sla_freshness_hours}h
            {routine.sla_breached && (
              <span className="ml-1 text-red-600 font-semibold">⚠ breached</span>
            )}
          </span>
        )}
      </div>

      {/* Last run info */}
      {routine.last_run ? (
        <div className="text-xs text-gray-600 flex flex-wrap gap-x-4 gap-y-1">
          <span>
            <span className="font-medium">Last run:</span>{" "}
            {formatIst(routine.last_run.ran_at)}
          </span>
          {routine.last_run.rows_inserted !== null && (
            <span>
              <span className="font-medium">Inserted:</span>{" "}
              {routine.last_run.rows_inserted?.toLocaleString("en-IN")}
            </span>
          )}
          {routine.last_run.duration_ms !== null && (
            <span>
              <span className="font-medium">Duration:</span>{" "}
              {routine.last_run.duration_ms}ms
            </span>
          )}
          {routine.last_run.error_message && (
            <span className="text-red-600 truncate max-w-xs" title={routine.last_run.error_message}>
              {routine.last_run.error_message}
            </span>
          )}
        </div>
      ) : !routine.is_new ? (
        <div className="text-xs text-gray-400 italic">No run data available</div>
      ) : null}

      {/* Source (for new routines) */}
      {routine.is_new && routine.source && (
        <div className="text-xs text-gray-400 truncate" title={routine.source}>
          <span className="font-medium">Source:</span> {routine.source}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary bar
// ---------------------------------------------------------------------------

function SummaryBar({ data }: { data: RoutinesResponse }) {
  return (
    <div className="flex flex-wrap gap-4 text-sm">
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-gray-400 inline-block" />
        <span className="text-gray-600">
          Total: <span className="font-semibold text-gray-900">{data.total}</span>
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
        <span className="text-gray-600">
          Live: <span className="font-semibold text-green-700">{data.live_count}</span>
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
        <span className="text-gray-600">
          SLA Breached:{" "}
          <span className="font-semibold text-red-700">{data.sla_breached_count}</span>
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
        <span className="text-gray-600">
          Planned:{" "}
          <span className="font-semibold text-blue-700">
            {data.routines.filter((r) => r.is_new).length}
          </span>
        </span>
      </div>
      {!data.data_available && (
        <div className="text-amber-600 text-xs font-medium">
          ⚠ de_routine_runs unavailable — showing manifest only
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function RoutinesPage() {
  let data: RoutinesResponse | null = null;
  let error: string | null = null;

  try {
    data = await getRoutines();
  } catch (err: unknown) {
    error = err instanceof Error ? err.message : String(err);
  }

  const existing = data?.routines.filter((r) => !r.is_new) ?? [];
  const planned = data?.routines.filter((r) => r.is_new) ?? [];

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Top bar matching forge chrome */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">
              Routine Visibility
            </h1>
            <p className="text-xs text-gray-400 mt-0.5">
              JIP data ingestion routines — manifest + live SLA status
            </p>
          </div>
          <div className="flex items-center gap-3">
            <a
              href="/forge"
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              ← Forge Dashboard
            </a>
            {data && (
              <span className="text-xs text-gray-400">
                as of {formatIst(data.as_of)}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load routine data: {error}
          </div>
        )}

        {data && (
          <>
            {/* Summary */}
            <div className="mb-6">
              <SummaryBar data={data} />
            </div>

            {/* Existing routines */}
            {existing.length > 0 && (
              <section className="mb-8">
                <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
                  Active Routines ({existing.length})
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {existing.map((r) => (
                    <RoutineCard key={r.id} routine={r} />
                  ))}
                </div>
              </section>
            )}

            {/* Planned routines */}
            {planned.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
                  Planned Routines ({planned.length})
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {planned.map((r) => (
                    <RoutineCard key={r.id} routine={r} />
                  ))}
                </div>
              </section>
            )}

            {data.routines.length === 0 && (
              <div className="text-center text-gray-400 py-16 text-sm">
                No routines found in manifest.
              </div>
            )}
          </>
        )}

        {!data && !error && (
          <div className="text-center text-gray-400 py-16 text-sm">Loading…</div>
        )}
      </div>
    </div>
  );
}
