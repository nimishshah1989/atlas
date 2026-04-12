"use client";

import { useEffect, useState } from "react";
import {
  getDecisions,
  actionDecision,
  type DecisionSummary,
} from "@/lib/api";
import { quadrantColor, quadrantBg } from "@/lib/format";

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
        {decisions.map((d) => (
          <div
            key={d.id}
            className="border rounded-lg p-3 hover:bg-gray-50"
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-[#1D9E75]">
                    {d.symbol}
                  </span>
                  <span
                    className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                      d.signal === "BUY"
                        ? "bg-emerald-50 text-emerald-700"
                        : d.signal === "SELL"
                          ? "bg-red-50 text-red-700"
                          : "bg-gray-50 text-gray-700"
                    }`}
                  >
                    {d.signal}
                  </span>
                  {d.quadrant && (
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded border ${quadrantBg(d.quadrant)} ${quadrantColor(d.quadrant)}`}
                    >
                      {d.quadrant}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600 mt-1">{d.reason}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {new Date(d.created_at).toLocaleString("en-IN", {
                    timeZone: "Asia/Kolkata",
                  })}
                </p>
              </div>

              {d.action === "PENDING" ? (
                <div className="flex gap-1.5">
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
                  className={`text-xs px-2 py-1 rounded ${
                    d.action === "ACCEPTED"
                      ? "bg-emerald-50 text-emerald-700"
                      : d.action === "IGNORED"
                        ? "bg-gray-100 text-gray-500"
                        : "bg-amber-50 text-amber-700"
                  }`}
                >
                  {d.action}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
