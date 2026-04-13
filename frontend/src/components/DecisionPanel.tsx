"use client";

import { useEffect, useState } from "react";
import {
  getDecisions,
  actionDecision,
  type DecisionSummary,
} from "@/lib/api";
import { quadrantColor, quadrantBg } from "@/lib/format";

/** Maps raw decision_type enum values to a display label. */
function decisionTypeLabel(dt: string): string {
  switch (dt) {
    case "BUY":
      return "BUY";
    case "SELL":
      return "SELL";
    case "HOLD":
      return "HOLD";
    case "WATCH":
      return "WATCH";
    case "buy_signal":
      return "BUY SIGNAL";
    case "sell_signal":
      return "SELL SIGNAL";
    case "overweight":
      return "OVERWEIGHT";
    case "avoid":
      return "AVOID";
    case "rotation":
      return "ROTATION";
    case "rebalance":
      return "REBALANCE";
    case "reduce_equity":
      return "REDUCE EQUITY";
    default:
      return dt.toUpperCase();
  }
}

/** CSS classes for decision_type badge */
function decisionTypeBadgeClass(dt: string): string {
  switch (dt) {
    case "BUY":
    case "buy_signal":
    case "overweight":
      return "bg-emerald-50 text-emerald-700";
    case "SELL":
    case "sell_signal":
    case "avoid":
    case "reduce_equity":
      return "bg-red-50 text-red-700";
    case "WATCH":
    case "rotation":
    case "rebalance":
      return "bg-amber-50 text-amber-700";
    default:
      return "bg-gray-50 text-gray-700";
  }
}

export default function DecisionPanel() {
  const [decisions, setDecisions] = useState<DecisionSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    getDecisions()
      .then((res) => setDecisions(res.decisions))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleAction = async (
    id: string,
    action: "ACCEPTED" | "IGNORED" | "OVERRIDDEN"
  ) => {
    await actionDecision(id, action);
    load();
  };

  if (loading) {
    return (
      <div className="animate-pulse space-y-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-16 bg-gray-100 rounded" />
        ))}
      </div>
    );
  }

  if (decisions.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 text-sm">
        No decisions yet. Decisions are generated when stocks change quadrants.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h2 className="text-lg font-semibold text-gray-800">Decisions</h2>
      <div className="space-y-2">
        {decisions.map((d) => {
          const userAction = d.user_action ?? "PENDING";
          const confidencePct = d.confidence
            ? `${Math.round(parseFloat(d.confidence) * 100)}%`
            : null;

          return (
            <div
              key={d.id}
              className="border rounded-lg p-3 hover:bg-gray-50"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-[#1D9E75]">
                      {d.entity}
                    </span>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded font-medium ${decisionTypeBadgeClass(d.decision_type)}`}
                      data-testid="decision-type-badge"
                    >
                      {decisionTypeLabel(d.decision_type)}
                    </span>
                    {confidencePct && (
                      <span className="text-xs text-gray-500">
                        {confidencePct}
                      </span>
                    )}
                    {d.horizon && (
                      <span className="text-xs text-gray-500">{d.horizon}</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-600 mt-1">{d.rationale}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <p className="text-xs text-gray-400">
                      {new Date(d.created_at).toLocaleString("en-IN", {
                        timeZone: "Asia/Kolkata",
                      })}
                    </p>
                    {d.source_agent && (
                      <span className="text-xs text-gray-400">
                        · {d.source_agent}
                      </span>
                    )}
                  </div>
                </div>

                {userAction === "PENDING" ? (
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      onClick={() => handleAction(d.id, "ACCEPTED")}
                      className="text-xs px-2 py-1 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                    >
                      Accept
                    </button>
                    <button
                      onClick={() => handleAction(d.id, "IGNORED")}
                      className="text-xs px-2 py-1 rounded bg-gray-50 text-gray-600 hover:bg-gray-100"
                    >
                      Ignore
                    </button>
                    <button
                      onClick={() => handleAction(d.id, "OVERRIDDEN")}
                      className="text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100"
                    >
                      Override
                    </button>
                  </div>
                ) : (
                  <span
                    className={`text-xs px-2 py-1 rounded shrink-0 ${
                      userAction === "ACCEPTED"
                        ? "bg-emerald-50 text-emerald-700"
                        : userAction === "IGNORED"
                          ? "bg-gray-100 text-gray-500"
                          : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {userAction}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
