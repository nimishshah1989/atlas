"use client";

export type LogPayload = {
  name: string;
  tail: string[];
  mtime: string;
};

export default function LogTail({ log }: { log: LogPayload | null }) {
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
        <span className="text-xs font-mono text-gray-700">{log.name}</span>
        <span className="text-[10px] font-mono text-gray-400">{log.mtime}</span>
      </div>
      <pre className="bg-gray-900 text-gray-100 text-[11px] font-mono leading-snug rounded p-3 overflow-x-auto max-h-[420px] whitespace-pre">
        {log.tail.join("\n") || "(empty)"}
      </pre>
    </div>
  );
}
