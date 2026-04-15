/** Shared helpers for /pro/global panels. */

export function formatIstDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export function formatIstDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
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

export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 bg-gray-100 rounded"
          style={{ width: `${60 + (i % 3) * 13}%` }}
        />
      ))}
    </div>
  );
}

export function PanelError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700 flex items-center justify-between">
      <span>{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="ml-3 text-red-600 underline hover:no-underline text-xs shrink-0"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function findingTypeColor(ft: string): string {
  switch (ft) {
    case "intermarket":
    case "inter_market":
      return "bg-teal-50 text-teal-700 border-teal-200";
    case "technical_analysis":
    case "technical":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "breadth_analysis":
    case "breadth":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "regime":
      return "bg-gray-50 text-gray-700 border-gray-200";
    case "macro":
      return "bg-purple-50 text-purple-700 border-purple-200";
    default:
      return "bg-gray-50 text-gray-600 border-gray-200";
  }
}

export function findingTypeLabel(ft: string): string {
  return ft
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function rsScoreColor(val: string | null): string {
  if (val === null || val === undefined) return "text-gray-400";
  const n = parseFloat(val);
  if (isNaN(n)) return "text-gray-400";
  if (n >= 1.1) return "text-emerald-600 font-semibold";
  if (n >= 1.0) return "text-emerald-500";
  if (n >= 0.9) return "text-amber-600";
  return "text-red-500";
}
