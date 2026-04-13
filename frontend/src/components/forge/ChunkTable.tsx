"use client";

export type ForgeChunk = {
  id: string;
  title: string;
  status: string;
  attempts: number;
  last_error: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};

const STATUS_COLOR: Record<string, string> = {
  DONE: "text-emerald-600 bg-emerald-50",
  FAILED: "text-red-600 bg-red-50",
  PLANNING: "text-amber-600 bg-amber-50",
  IMPLEMENTING: "text-teal-600 bg-teal-50",
  TESTING: "text-teal-600 bg-teal-50",
  QUALITY_CHECK: "text-teal-600 bg-teal-50",
  PENDING: "text-gray-500 bg-gray-100",
  BLOCKED: "text-gray-500 bg-gray-100",
};

export default function ChunkTable({ chunks }: { chunks: ForgeChunk[] }) {
  if (chunks.length === 0) {
    return (
      <p className="text-xs text-gray-500 font-mono">
        No chunks found. Has the orchestrator initialized state.db?
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] uppercase tracking-wider text-gray-500 border-b">
            <th className="py-2 pr-2">ID</th>
            <th className="py-2 pr-2">Title</th>
            <th className="py-2 pr-2">Status</th>
            <th className="py-2 pr-2 text-right">Att.</th>
            <th className="py-2 pr-2 font-mono">Updated</th>
          </tr>
        </thead>
        <tbody>
          {chunks.map((c) => {
            const color = STATUS_COLOR[c.status] ?? "text-gray-600 bg-gray-100";
            return (
              <tr
                key={c.id}
                className="border-b border-gray-100 last:border-0"
              >
                <td className="py-1.5 pr-2 font-mono text-xs text-gray-700">
                  {c.id}
                </td>
                <td className="py-1.5 pr-2 text-gray-800">{c.title}</td>
                <td className="py-1.5 pr-2">
                  <span
                    className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded ${color}`}
                  >
                    {c.status}
                  </span>
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums text-xs text-gray-600">
                  {c.attempts}
                </td>
                <td className="py-1.5 pr-2 font-mono text-[10px] text-gray-500">
                  {c.updated_at?.slice(0, 19).replace("T", " ")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
