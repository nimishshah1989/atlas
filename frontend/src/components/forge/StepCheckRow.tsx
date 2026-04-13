"use client";

import { useState } from "react";
import type { CheckEnum, StepResponse } from "@/lib/systemClient";

// ---------------------------------------------------------------------------
// Icons & colors per check enum
// ---------------------------------------------------------------------------

const CHECK_ICON: Record<CheckEnum, string> = {
  ok: "✓",
  fail: "✗",
  "slow-skipped": "⋯",
  error: "⚠",
};

const CHECK_COLOR: Record<CheckEnum, string> = {
  ok: "text-emerald-600",
  fail: "text-red-600",
  "slow-skipped": "text-gray-400",
  error: "text-amber-600",
};

// ---------------------------------------------------------------------------
// StepCheckRow
// ---------------------------------------------------------------------------

export default function StepCheckRow({ step }: { step: StepResponse }) {
  const [showDetail, setShowDetail] = useState(false);
  const hasDetail = Boolean(step.detail);

  return (
    <div className="pl-8">
      <div
        className={`flex items-start gap-2 py-0.5 ${hasDetail ? "cursor-pointer" : ""}`}
        onClick={() => hasDetail && setShowDetail((v) => !v)}
        title={hasDetail ? "Click to toggle detail" : undefined}
      >
        <span
          className={`font-mono text-xs font-bold flex-shrink-0 w-3 ${CHECK_COLOR[step.check]}`}
        >
          {CHECK_ICON[step.check]}
        </span>
        <span className="text-xs text-gray-700 font-mono">{step.id}</span>
        <span className="text-xs text-gray-600 flex-1">{step.text}</span>
        {hasDetail && (
          <span className="text-[10px] text-gray-400 font-mono flex-shrink-0">
            {showDetail ? "▲" : "▼"}
          </span>
        )}
      </div>
      {showDetail && step.detail && (
        <div className="ml-5 mt-0.5 mb-1 px-2 py-1.5 bg-gray-50 rounded border border-gray-200">
          <pre className="text-[10px] font-mono text-gray-600 whitespace-pre-wrap break-all">
            {step.detail}
          </pre>
        </div>
      )}
    </div>
  );
}
