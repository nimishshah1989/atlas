"use client";

import { useState } from "react";

export type ContextFile = {
  key: string;
  label: string;
  group: "architect" | "memory" | "wiki" | "spec";
  relPath: string;
  exists: boolean;
  mtime: string | null;
  size: number | null;
};

const GROUP_LABEL: Record<ContextFile["group"], string> = {
  architect: "Architect",
  spec: "Spec",
  memory: "Auto-memory",
  wiki: "Forge wiki",
};

const GROUP_COLOR: Record<ContextFile["group"], string> = {
  architect: "text-[#1D9E75] bg-emerald-50",
  spec: "text-indigo-600 bg-indigo-50",
  memory: "text-amber-700 bg-amber-50",
  wiki: "text-teal-600 bg-teal-50",
};

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const s = Math.round((now - then) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function formatAbsolute(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 19).replace("T", " ");
}

function formatSize(n: number | null): string {
  if (n === null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1_048_576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1_048_576).toFixed(1)} MB`;
}

export default function ContextFiles({ files }: { files: ContextFile[] }) {
  // Collapsed by default (demoted panel)
  const [collapsed, setCollapsed] = useState(true);
  const [open, setOpen] = useState<ContextFile | null>(null);
  const [body, setBody] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const view = async (file: ContextFile) => {
    setOpen(file);
    setBody("");
    setErr(null);
    setLoading(true);
    try {
      const res = await fetch(
        `/forge/api/file?key=${encodeURIComponent(file.key)}`,
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBody(await res.text());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Collapsed toggle */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-gray-500 hover:text-gray-700 mb-2"
      >
        <span>{collapsed ? "▶" : "▼"}</span>
        <span>Context files ({files.length})</span>
        <span className="text-gray-400">— read by every chunk at boot</span>
      </button>

      {!collapsed && (
        <>
          {files.length === 0 ? (
            <p className="text-xs text-gray-500 font-mono">
              No context files discovered.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-gray-500 border-b">
                    <th className="py-2 pr-2">Group</th>
                    <th className="py-2 pr-2">File</th>
                    <th className="py-2 pr-2 font-mono">Path</th>
                    <th className="py-2 pr-2 text-right">Size</th>
                    <th className="py-2 pr-2 font-mono">Last updated</th>
                    <th className="py-2 pr-2 text-right">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((f) => (
                    <tr
                      key={f.key}
                      className="border-b border-gray-100 last:border-0"
                    >
                      <td className="py-1.5 pr-2">
                        <span
                          className={`text-[10px] font-mono uppercase px-1.5 py-0.5 rounded ${GROUP_COLOR[f.group]}`}
                        >
                          {GROUP_LABEL[f.group]}
                        </span>
                      </td>
                      <td className="py-1.5 pr-2 text-gray-800">{f.label}</td>
                      <td className="py-1.5 pr-2 font-mono text-[10px] text-gray-500">
                        {f.relPath}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums text-xs text-gray-600">
                        {formatSize(f.size)}
                      </td>
                      <td
                        className="py-1.5 pr-2 font-mono text-[10px] text-gray-500"
                        title={formatAbsolute(f.mtime)}
                      >
                        {f.exists ? (
                          formatRelative(f.mtime)
                        ) : (
                          <span className="text-red-600">missing</span>
                        )}
                      </td>
                      <td className="py-1.5 pr-2 text-right">
                        <button
                          onClick={() => view(f)}
                          disabled={!f.exists}
                          className="text-[10px] font-mono uppercase px-2 py-0.5 rounded border border-[#1D9E75] text-[#1D9E75] hover:bg-emerald-50 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          view
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={() => setOpen(null)}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between border-b px-4 py-3">
              <div>
                <h3 className="text-sm font-bold">{open.label}</h3>
                <p className="text-[10px] font-mono text-gray-500">
                  {open.relPath} ·{" "}
                  {open.mtime ? `updated ${formatRelative(open.mtime)}` : ""}
                </p>
              </div>
              <button
                onClick={() => setOpen(null)}
                className="text-xs font-mono text-gray-500 hover:text-gray-900"
              >
                close ✕
              </button>
            </header>
            <div className="overflow-auto p-4">
              {loading && (
                <p className="text-xs text-gray-500 font-mono">loading…</p>
              )}
              {err && (
                <p className="text-xs text-red-600 font-mono">{err}</p>
              )}
              {!loading && !err && (
                <pre className="text-[11px] font-mono whitespace-pre-wrap break-words text-gray-800">
                  {body}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
