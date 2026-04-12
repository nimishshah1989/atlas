/** Indian number formatting — lakh/crore, not million/billion. */

export function formatIndianNumber(num: number): string {
  if (num === 0) return "0";
  const isNeg = num < 0;
  const abs = Math.abs(num);

  if (abs >= 1_00_00_000) {
    return `${isNeg ? "-" : ""}${(abs / 1_00_00_000).toFixed(2)} Cr`;
  }
  if (abs >= 1_00_000) {
    return `${isNeg ? "-" : ""}${(abs / 1_00_000).toFixed(2)} L`;
  }

  // Indian comma grouping
  const str = abs.toFixed(0);
  const parts = [];
  let i = str.length;
  parts.unshift(str.slice(Math.max(0, i - 3), i));
  i -= 3;
  while (i > 0) {
    parts.unshift(str.slice(Math.max(0, i - 2), i));
    i -= 2;
  }
  return `${isNeg ? "-" : ""}${parts.join(",")}`;
}

export function formatCurrency(val: number | string | null): string {
  if (val === null || val === undefined) return "—";
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "—";
  return `₹${formatIndianNumber(num)}`;
}

export function formatDecimal(
  val: string | number | null,
  decimals = 2
): string {
  if (val === null || val === undefined) return "—";
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "—";
  return num.toFixed(decimals);
}

export function formatPercent(
  val: string | number | null,
  showSign = true
): string {
  if (val === null || val === undefined) return "—";
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "—";
  const sign = showSign && num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}%`;
}

export function formatRs(val: string | number | null): string {
  if (val === null || val === undefined) return "—";
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "—";
  const sign = num > 0 ? "+" : "";
  return `${sign}${num.toFixed(2)}`;
}

export function quadrantColor(q: string | null): string {
  switch (q) {
    case "LEADING":
      return "text-emerald-600";
    case "IMPROVING":
      return "text-blue-600";
    case "WEAKENING":
      return "text-amber-600";
    case "LAGGING":
      return "text-red-600";
    default:
      return "text-gray-500";
  }
}

export function quadrantBg(q: string | null): string {
  switch (q) {
    case "LEADING":
      return "bg-emerald-50 border-emerald-200";
    case "IMPROVING":
      return "bg-blue-50 border-blue-200";
    case "WEAKENING":
      return "bg-amber-50 border-amber-200";
    case "LAGGING":
      return "bg-red-50 border-red-200";
    default:
      return "bg-gray-50 border-gray-200";
  }
}

export function regimeColor(r: string): string {
  switch (r) {
    case "BULL":
      return "text-emerald-700 bg-emerald-50";
    case "BEAR":
      return "text-red-700 bg-red-50";
    case "SIDEWAYS":
      return "text-amber-700 bg-amber-50";
    case "RECOVERY":
      return "text-blue-700 bg-blue-50";
    default:
      return "text-gray-700 bg-gray-50";
  }
}

export function signColor(val: string | number | null): string {
  if (val === null || val === undefined) return "";
  const num = typeof val === "string" ? parseFloat(val) : val;
  if (isNaN(num)) return "";
  return num > 0 ? "text-emerald-600" : num < 0 ? "text-red-600" : "";
}
