// frontend/src/lib/tv.ts
export type TvLabel = "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL";

export interface TvChip {
  label: TvLabel | null;
  score: number | null;
  className: string;
  display: string;
}

const CLASS_BY_LABEL: Record<TvLabel, string> = {
  STRONG_BUY: "bg-emerald-50 text-emerald-700 border-emerald-200",
  BUY: "bg-emerald-50/50 text-emerald-600 border-emerald-100",
  NEUTRAL: "bg-gray-50 text-gray-600 border-gray-200",
  SELL: "bg-red-50/50 text-red-600 border-red-100",
  STRONG_SELL: "bg-red-50 text-red-700 border-red-200",
};
const NEUTRAL_CLASS = "bg-white text-gray-400 border-gray-200";

export function classifyTvScore(raw: unknown): TvChip {
  const score = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
  if (score === null) {
    return { label: null, score: null, className: NEUTRAL_CLASS, display: "—" };
  }
  let label: TvLabel;
  if (score >= 0.5) label = "STRONG_BUY";
  else if (score >= 0.1) label = "BUY";
  else if (score > -0.1) label = "NEUTRAL";
  else if (score > -0.5) label = "SELL";
  else label = "STRONG_SELL";
  const sign = score > 0 ? "+" : "";
  return {
    label,
    score,
    className: CLASS_BY_LABEL[label],
    display: `${sign}${score.toFixed(2)}`,
  };
}
