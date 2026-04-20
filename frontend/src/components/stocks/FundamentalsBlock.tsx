"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";

interface FundamentalsData {
  market_cap_cr?: string | null;
  pe_ratio?: string | null;
  pb_ratio?: string | null;
  peg_ratio?: string | null;
  ev_ebitda?: string | null;
  roe_pct?: string | null;
  roce_pct?: string | null;
  operating_margin_pct?: string | null;
  net_margin_pct?: string | null;
  debt_to_equity?: string | null;
  eps_ttm?: string | null;
  book_value?: string | null;
  dividend_yield_pct?: string | null;
  promoter_holding_pct?: string | null;
  pledged_pct?: string | null;
  fii_holding_pct?: string | null;
  dii_holding_pct?: string | null;
  revenue_growth_yoy_pct?: string | null;
  profit_growth_yoy_pct?: string | null;
  high_52w?: string | null;
  low_52w?: string | null;
  face_value?: string | null;
  [key: string]: unknown;
}

interface FundamentalsBlockProps {
  symbol: string;
}

function num(v: string | null | undefined, dp = 2): string {
  if (v == null || v === "") return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  return n.toFixed(dp);
}

function pctSign(v: string | null | undefined, dp = 1): string {
  if (v == null || v === "") return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(dp)}%`;
}

function formatCr(v: string | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}L Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${n.toFixed(0)} Cr`;
}

function valColor(v: string | null | undefined, higherGood = true): string {
  if (v == null) return "var(--text-primary)";
  const n = parseFloat(v);
  if (isNaN(n)) return "var(--text-primary)";
  const good = higherGood ? n >= 0 : n <= 0;
  return good ? "var(--rag-green-700)" : "var(--rag-red-700)";
}

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid var(--border-subtle)" }}>
      <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, fontFamily: "var(--font-mono)", color: color ?? "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

export default function FundamentalsBlock({ symbol }: FundamentalsBlockProps) {
  const { data, meta, state, error } = useAtlasData<FundamentalsData>(
    `/api/v1/stocks/${symbol}/fundamentals`,
    undefined,
    { dataClass: "fundamentals" }
  );

  const hasAny = data != null && Object.values(data).some(v => v != null);
  const effectiveState = state === "ready" && !hasAny ? "empty" : state;

  return (
    <div data-block="fundamentals">
      <DataBlock
        state={effectiveState}
        dataClass="fundamentals"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No fundamentals data"
        emptyBody="Fundamentals are not available for this stock."
      >
        {data && hasAny && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-4)" }}>

            {/* Valuation */}
            <div style={{ background: "var(--bg-surface)", border: "var(--border-card)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: "var(--space-3)" }}>
                Valuation
              </div>
              <MetricRow label="Market Cap" value={formatCr(data.market_cap_cr)} />
              <MetricRow label="P/E Ratio" value={num(data.pe_ratio, 1)} />
              <MetricRow label="P/B Ratio" value={num(data.pb_ratio, 2)} />
              <MetricRow label="EPS (TTM)" value={data.eps_ttm ? `₹${num(data.eps_ttm, 2)}` : "—"} />
              <MetricRow label="Book Value" value={data.book_value ? `₹${num(data.book_value, 0)}` : "—"} />
              {data.face_value && <MetricRow label="Face Value" value={`₹${num(data.face_value, 0)}`} />}
            </div>

            {/* Profitability */}
            <div style={{ background: "var(--bg-surface)", border: "var(--border-card)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: "var(--space-3)" }}>
                Profitability
              </div>
              <MetricRow label="ROE" value={data.roe_pct ? `${num(data.roe_pct, 1)}%` : "—"} color={valColor(data.roe_pct)} />
              <MetricRow label="ROCE" value={data.roce_pct ? `${num(data.roce_pct, 1)}%` : "—"} color={valColor(data.roce_pct)} />
              <MetricRow label="Operating Margin" value={data.operating_margin_pct ? `${num(data.operating_margin_pct, 1)}%` : "—"} color={valColor(data.operating_margin_pct)} />
              <MetricRow label="Net Margin" value={data.net_margin_pct ? `${num(data.net_margin_pct, 1)}%` : "—"} color={valColor(data.net_margin_pct)} />
              <MetricRow label="Rev Growth (YoY)" value={pctSign(data.revenue_growth_yoy_pct)} color={valColor(data.revenue_growth_yoy_pct)} />
              <MetricRow label="Profit Growth (YoY)" value={pctSign(data.profit_growth_yoy_pct)} color={valColor(data.profit_growth_yoy_pct)} />
            </div>

            {/* Ownership & Others */}
            <div style={{ background: "var(--bg-surface)", border: "var(--border-card)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--text-tertiary)", marginBottom: "var(--space-3)" }}>
                Ownership &amp; Risk
              </div>
              {data.promoter_holding_pct && <MetricRow label="Promoter %" value={`${num(data.promoter_holding_pct, 1)}%`} />}
              {data.fii_holding_pct && <MetricRow label="FII %" value={`${num(data.fii_holding_pct, 2)}%`} />}
              {data.dii_holding_pct && <MetricRow label="DII %" value={`${num(data.dii_holding_pct, 2)}%`} />}
              {data.pledged_pct != null && <MetricRow label="Pledged %" value={`${num(data.pledged_pct, 1)}%`} color={parseFloat(data.pledged_pct ?? "0") > 20 ? "var(--rag-red-700)" : undefined} />}
              <MetricRow label="Debt / Equity" value={num(data.debt_to_equity, 2)} color={parseFloat(data.debt_to_equity ?? "0") > 1 ? "var(--rag-amber-700)" : undefined} />
              <MetricRow label="Dividend Yield" value={data.dividend_yield_pct ? `${num(data.dividend_yield_pct, 2)}%` : "—"} />
              {data.high_52w && data.low_52w && (
                <MetricRow label="52W Range" value={`₹${num(data.low_52w, 0)} – ₹${num(data.high_52w, 0)}`} />
              )}
            </div>

          </div>
        )}
      </DataBlock>
    </div>
  );
}
