"use client";

/**
 * FourLensCard + FourLensRow — the consistent 4-lens display used everywhere in ATLAS.
 *
 * The four lenses are the locked framework for every level of the drill hierarchy
 * (global → country → sector → instrument):
 *
 *   1. RS         — relative strength vs a benchmark (NIFTY 500 by default)
 *   2. MOMENTUM   — RS1m - RS3m (slope) or ROC
 *   3. BREADTH    — % of constituents participating (e.g. above 50-DMA)
 *   4. VOLUME     — volume ratio vs 20-day average (participation confirm)
 *
 * Design principle: every lens shows a 0-100 or a signed-delta value with a
 * semantic color (green / amber / red) and a one-line tooltip explaining the
 * calc. Missing data → "—" + muted color. Never show "0" where we mean null.
 */

import React from "react";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface LensValue {
  /** Numeric value (0-100 for percentile-normalised lenses, or signed delta) */
  value: number | null;
  /** Short display label, e.g. "72.3" or "+5.2" */
  display?: string;
  /** Tone: derived from value thresholds if omitted */
  tone?: "strong" | "neutral" | "weak" | "unknown";
  /** Optional context badge, e.g. "RS1m" or "vs N500" */
  sub?: string;
}

export interface FourLens {
  rs: LensValue;
  momentum: LensValue;
  breadth: LensValue;
  volume: LensValue;
}

export type LensKind = "rs" | "momentum" | "breadth" | "volume";

const LENS_LABELS: Record<LensKind, string> = {
  rs: "RS",
  momentum: "Momentum",
  breadth: "Breadth",
  volume: "Volume",
};

const LENS_TOOLTIPS: Record<LensKind, string> = {
  rs: "Relative strength vs benchmark (0-100 percentile, NIFTY 500 default)",
  momentum: "RS slope: RS1m minus RS3m. Positive = accelerating.",
  breadth: "Participation: % of constituents above their 50-DMA",
  volume: "Volume ratio vs 20-day average (>1.0 means above-avg participation)",
};

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function resolveTone(kind: LensKind, value: number | null, explicit?: LensValue["tone"]): LensValue["tone"] {
  if (explicit) return explicit;
  if (value === null || Number.isNaN(value)) return "unknown";

  // RS + Breadth: 0-100 scale, >60 strong, 40-60 neutral, <40 weak
  if (kind === "rs" || kind === "breadth") {
    if (value >= 60) return "strong";
    if (value >= 40) return "neutral";
    return "weak";
  }
  // Momentum: signed. >+2 strong, -2..+2 neutral, <-2 weak
  if (kind === "momentum") {
    if (value > 2) return "strong";
    if (value < -2) return "weak";
    return "neutral";
  }
  // Volume ratio: >1.2 strong, 0.8-1.2 neutral, <0.8 weak
  if (value >= 1.2) return "strong";
  if (value >= 0.8) return "neutral";
  return "weak";
}

function toneColor(tone: LensValue["tone"]): { fg: string; bg: string; border: string } {
  switch (tone) {
    case "strong":
      return { fg: "var(--rag-green-700)", bg: "var(--rag-green-100)", border: "var(--rag-green-300)" };
    case "weak":
      return { fg: "var(--rag-red-700)", bg: "var(--rag-red-100)", border: "var(--rag-red-300)" };
    case "neutral":
      return { fg: "var(--rag-amber-700)", bg: "var(--rag-amber-100)", border: "var(--rag-amber-300)" };
    default:
      return { fg: "var(--text-tertiary)", bg: "var(--bg-inset)", border: "var(--border-default)" };
  }
}

function formatValue(kind: LensKind, v: LensValue): string {
  if (v.display) return v.display;
  if (v.value === null || Number.isNaN(v.value)) return "—";
  if (kind === "momentum") {
    const sign = v.value > 0 ? "+" : "";
    return `${sign}${v.value.toFixed(1)}`;
  }
  if (kind === "volume") {
    return `${v.value.toFixed(2)}×`;
  }
  return v.value.toFixed(1);
}

// ─────────────────────────────────────────────────────────────────────────────
// LensPill — single lens chip
// ─────────────────────────────────────────────────────────────────────────────

export interface LensPillProps {
  kind: LensKind;
  value: LensValue;
  size?: "sm" | "md" | "lg";
  /** If true, render as a compact chip inline (for table rows) */
  compact?: boolean;
}

export function LensPill({ kind, value, size = "md", compact = false }: LensPillProps) {
  const tone = resolveTone(kind, value.value, value.tone);
  const colors = toneColor(tone);
  const display = formatValue(kind, value);

  const pad = size === "sm" ? "2px 6px" : size === "lg" ? "8px 12px" : "4px 10px";
  const fs = size === "sm" ? 11 : size === "lg" ? 18 : 13;
  const labelFs = size === "sm" ? 9 : size === "lg" ? 11 : 10;

  if (compact) {
    return (
      <span
        title={LENS_TOOLTIPS[kind]}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          padding: "1px 6px",
          borderRadius: "var(--radius-sm)",
          background: colors.bg,
          border: `1px solid ${colors.border}`,
          color: colors.fg,
          fontSize: 11,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 600,
          lineHeight: 1.4,
        }}
        data-lens={kind}
        data-tone={tone}
      >
        {display}
      </span>
    );
  }

  return (
    <div
      title={LENS_TOOLTIPS[kind]}
      style={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "flex-start",
        padding: pad,
        borderRadius: "var(--radius-md)",
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        minWidth: size === "lg" ? 96 : 72,
      }}
      data-lens={kind}
      data-tone={tone}
    >
      <span
        style={{
          fontSize: labelFs,
          fontWeight: 600,
          color: colors.fg,
          letterSpacing: "var(--tracking-wide)",
          textTransform: "uppercase",
          opacity: 0.85,
          lineHeight: 1.2,
        }}
      >
        {LENS_LABELS[kind]}
        {value.sub ? <span style={{ marginLeft: 4, opacity: 0.7 }}>{value.sub}</span> : null}
      </span>
      <span
        style={{
          fontSize: fs,
          fontWeight: 700,
          color: colors.fg,
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.2,
          marginTop: 2,
        }}
      >
        {display}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// FourLensCard — hero-sized display for a single entity (country/sector/stock)
// ─────────────────────────────────────────────────────────────────────────────

export interface FourLensCardProps {
  lenses: FourLens;
  size?: "sm" | "md" | "lg";
  title?: string;
  subtitle?: string;
  /** Bench marker for RS (e.g. "NIFTY 500", "GOLD") */
  benchmark?: string;
}

export function FourLensCard({ lenses, size = "md", title, subtitle, benchmark }: FourLensCardProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        padding: size === "lg" ? "var(--space-4)" : "var(--space-3)",
        background: "var(--bg-surface)",
        border: "var(--border-card)",
        borderRadius: "var(--radius-lg)",
      }}
      data-component="four-lens-card"
    >
      {(title || subtitle) && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {title && (
            <div
              style={{
                fontSize: size === "lg" ? "var(--fs-lg)" : "var(--fs-md)",
                fontWeight: 600,
                color: "var(--text-primary)",
                fontFamily: "var(--font-sans)",
              }}
            >
              {title}
            </div>
          )}
          {subtitle && (
            <div
              style={{
                fontSize: "var(--fs-xs)",
                color: "var(--text-tertiary)",
                textTransform: "uppercase",
                letterSpacing: "var(--tracking-wide)",
              }}
            >
              {subtitle}
              {benchmark ? ` · vs ${benchmark}` : ""}
            </div>
          )}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--space-2)" }}>
        <LensPill kind="rs" value={lenses.rs} size={size} />
        <LensPill kind="momentum" value={lenses.momentum} size={size} />
        <LensPill kind="breadth" value={lenses.breadth} size={size} />
        <LensPill kind="volume" value={lenses.volume} size={size} />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// FourLensRow — compact inline display for table cells
// ─────────────────────────────────────────────────────────────────────────────

export interface FourLensRowProps {
  lenses: FourLens;
}

export function FourLensRow({ lenses }: FourLensRowProps) {
  return (
    <div
      style={{
        display: "inline-flex",
        gap: 4,
        alignItems: "center",
      }}
      data-component="four-lens-row"
    >
      <LensPill kind="rs" value={lenses.rs} compact />
      <LensPill kind="momentum" value={lenses.momentum} compact />
      <LensPill kind="breadth" value={lenses.breadth} compact />
      <LensPill kind="volume" value={lenses.volume} compact />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Safe builder — forgives missing fields
// ─────────────────────────────────────────────────────────────────────────────

export function buildFourLens(partial: {
  rs?: number | string | null;
  momentum?: number | string | null;
  breadth?: number | string | null;
  volume?: number | string | null;
  rsSub?: string;
}): FourLens {
  const toNum = (v: number | string | null | undefined): number | null => {
    if (v === null || v === undefined || v === "") return null;
    const n = typeof v === "number" ? v : parseFloat(v);
    return Number.isFinite(n) ? n : null;
  };
  return {
    rs: { value: toNum(partial.rs), sub: partial.rsSub },
    momentum: { value: toNum(partial.momentum) },
    breadth: { value: toNum(partial.breadth) },
    volume: { value: toNum(partial.volume) },
  };
}
