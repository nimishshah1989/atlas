"use client";

import type { LogsTailResponse } from "@/lib/systemClient";

export default function LogTail({ log }: { log: LogsTailResponse | null }) {
  if (!log) {
    return (
      <p className="text-xs text-gray-500 font-mono">
        No orchestrator logs yet.
      </p>
    );
  }
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-mono text-gray-700">{log.file}</span>
        <span className="text-[10px] font-mono text-gray-400">
          {log.as_of.slice(0, 19).replace("T", " ")}
        </span>
      </div>
      <pre className="bg-gray-900 text-gray-100 text-[11px] font-mono leading-snug rounded p-3 overflow-x-auto max-h-[420px] whitespace-pre">
        {log.lines.join("\n") || "(empty)"}
      </pre>
    </div>
  );
}
