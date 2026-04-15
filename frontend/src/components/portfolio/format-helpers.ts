/** Portfolio-specific formatting helpers. */

import type { HoldingAnalysis } from "@/lib/api-portfolio";

export function fmtWeight(val: string | null): string {
  if (!val) return "\u2014";
  const n = parseFloat(val);
  if (isNaN(n)) return "\u2014";
  return `${(n * 100).toFixed(1)}%`;
}

export function fmtEffect(val: string | null): string {
  if (!val) return "\u2014";
  const n = parseFloat(val);
  if (isNaN(n)) return "\u2014";
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(3)}%`;
}

export function effectColor(val: string | null): string {
  if (!val) return "";
  const n = parseFloat(val);
  if (isNaN(n)) return "";
  return n > 0 ? "text-emerald-600" : n < 0 ? "text-red-600" : "";
}

export function exportHoldingsCsv(holdings: HoldingAnalysis[]) {
  const headers = [
    "Scheme Name",
    "Units",
    "NAV",
    "Current Value",
    "Weight %",
    "Return 1Y",
    "RS Composite",
    "Quadrant",
    "Sharpe Ratio",
  ];

  const rows = holdings.map((h) => [
    `"${h.scheme_name.replace(/"/g, '""')}"`,
    h.units,
    h.nav ?? "",
    h.current_value ?? "",
    h.weight_pct ? (parseFloat(h.weight_pct) * 100).toFixed(2) : "",
    h.return_1y ?? "",
    h.rs_composite ?? "",
    h.quadrant ?? "",
    h.sharpe_ratio ?? "",
  ]);

  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "holdings.csv";
  a.click();
  URL.revokeObjectURL(url);
}
