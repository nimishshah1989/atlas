"use client";

import { useAtlasData } from "@/hooks/useAtlasData";
import DataBlock from "@/components/ui/DataBlock";
import { formatDate } from "@/lib/format";

interface CorporateAction {
  ex_date: string | null;
  action_type: string | null;
  dividend_type?: string | null;
  ratio_from?: string | null;
  ratio_to?: string | null;
  cash_value?: string | null;
  notes?: string | null;
}

type CorporateActionsData = CorporateAction[];

interface CorporateActionsBlockProps {
  symbol: string;
}

function actionLabel(action: CorporateAction): string {
  const t = (action.action_type ?? "").toLowerCase();
  if (t === "dividend") {
    const dt = (action.dividend_type ?? "").toLowerCase();
    return dt ? `${dt.charAt(0).toUpperCase() + dt.slice(1)} Dividend` : "Dividend";
  }
  if (t === "bonus") {
    if (action.ratio_from && action.ratio_to) {
      return `Bonus ${action.ratio_to}:${action.ratio_from}`;
    }
    return "Bonus Issue";
  }
  if (t === "split") {
    if (action.ratio_from && action.ratio_to) {
      return `Split ${action.ratio_to}:${action.ratio_from}`;
    }
    return "Stock Split";
  }
  if (t === "rights") return "Rights Issue";
  return action.action_type ?? "—";
}

function actionBadgeStyle(actionType: string | null): React.CSSProperties {
  const t = (actionType ?? "").toLowerCase();
  if (t === "dividend")  return { background: "var(--rag-green-100)", color: "var(--rag-green-700)", border: "1px solid var(--rag-green-200)" };
  if (t === "bonus")     return { background: "#dbeafe", color: "#1d4ed8", border: "1px solid #bfdbfe" };
  if (t === "split")     return { background: "#f3e8ff", color: "#7c3aed", border: "1px solid #e9d5ff" };
  if (t === "rights")    return { background: "var(--rag-amber-100)", color: "var(--rag-amber-700)", border: "1px solid var(--rag-amber-200)" };
  return { background: "var(--bg-inset)", color: "var(--text-secondary)", border: "1px solid var(--border-default)" };
}

export default function CorporateActionsBlock({ symbol }: CorporateActionsBlockProps) {
  const { data, meta, state, error } = useAtlasData<CorporateActionsData>(
    `/api/v1/stocks/${symbol}/corporate-actions`,
    undefined,
    { dataClass: "fundamentals" }
  );

  const actions: CorporateAction[] = Array.isArray(data) ? data : [];
  const effectiveState = state === "ready" && actions.length === 0 ? "empty" : state;

  return (
    <div data-block="corporate-actions">
      <DataBlock
        state={effectiveState}
        dataClass="fundamentals"
        dataAsOf={meta?.data_as_of ?? null}
        errorCode={error?.code}
        errorMessage={error?.message}
        emptyTitle="No corporate actions"
        emptyBody="No dividends, splits or bonuses found for this stock."
      >
        {actions.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-default)", background: "var(--bg-inset)" }}>
                  <th style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em" }}>Ex-Date</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em" }}>Action</th>
                  <th style={{ padding: "8px 12px", textAlign: "right", fontSize: 11, fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: ".05em" }}>Details</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((a, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>
                      {formatDate(a.ex_date ?? null)}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <span style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        borderRadius: "var(--radius-full)",
                        fontSize: 11,
                        fontWeight: 600,
                        ...actionBadgeStyle(a.action_type),
                      }}>
                        {actionLabel(a)}
                      </span>
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "right", fontSize: 11, color: "var(--text-tertiary)" }}>
                      {a.cash_value ? `₹${a.cash_value} / share` : a.notes ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </DataBlock>
    </div>
  );
}
