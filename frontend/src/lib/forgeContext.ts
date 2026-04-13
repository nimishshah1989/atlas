import { readdirSync, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";

// Where the Next.js app runs: /home/ubuntu/atlas/frontend.
// REPO_ROOT is the atlas repo one level up.
const REPO_ROOT = path.resolve(process.cwd(), "..");
const HOME = os.homedir();
const MEMORY_DIR = path.join(
  HOME,
  ".claude",
  "projects",
  "-home-ubuntu-atlas",
  "memory"
);
const FORGE_WIKI_DIR = path.join(HOME, ".forge", "knowledge", "wiki");

export type ContextFile = {
  key: string;
  label: string;
  group: "architect" | "memory" | "wiki" | "spec";
  relPath: string; // user-facing display path (absolute, abbreviated home)
  exists: boolean;
  mtime: string | null;
  size: number | null;
};

type Entry = { key: string; label: string; group: ContextFile["group"]; abs: string };

function abbreviate(p: string): string {
  return p.startsWith(HOME) ? "~" + p.slice(HOME.length) : p;
}

function stat(abs: string): { exists: boolean; mtime: string | null; size: number | null } {
  try {
    const s = statSync(abs);
    return {
      exists: true,
      mtime: new Date(s.mtimeMs).toISOString(),
      size: s.size,
    };
  } catch {
    return { exists: false, mtime: null, size: null };
  }
}

function pinned(): Entry[] {
  return [
    {
      key: "claude_md",
      label: "CLAUDE.md (architect)",
      group: "architect",
      abs: path.join(REPO_ROOT, "CLAUDE.md"),
    },
    {
      key: "spec",
      label: "ATLAS-DEFINITIVE-SPEC.md",
      group: "spec",
      abs: path.join(REPO_ROOT, "ATLAS-DEFINITIVE-SPEC.md"),
    },
    {
      key: "memory_index",
      label: "MEMORY.md (auto-memory index)",
      group: "memory",
      abs: path.join(MEMORY_DIR, "MEMORY.md"),
    },
    {
      key: "wiki_index",
      label: "Forge wiki index.md",
      group: "wiki",
      abs: path.join(FORGE_WIKI_DIR, "index.md"),
    },
  ];
}

function memoryFiles(): Entry[] {
  try {
    return readdirSync(MEMORY_DIR)
      .filter((f) => f.endsWith(".md") && f !== "MEMORY.md")
      .sort()
      .map((f) => ({
        key: `memory:${f}`,
        label: f,
        group: "memory" as const,
        abs: path.join(MEMORY_DIR, f),
      }));
  } catch {
    return [];
  }
}

// Allowlist map: key → absolute path. Built fresh per request so newly
// added memory files show up without a server restart. Any file endpoint
// must look up its key here — never resolve user-supplied paths.
export function buildAllowlist(): Map<string, Entry> {
  const map = new Map<string, Entry>();
  for (const e of [...pinned(), ...memoryFiles()]) {
    map.set(e.key, e);
  }
  return map;
}

export function listContextFiles(): ContextFile[] {
  const out: ContextFile[] = [];
  for (const entry of buildAllowlist().values()) {
    const s = stat(entry.abs);
    out.push({
      key: entry.key,
      label: entry.label,
      group: entry.group,
      relPath: abbreviate(entry.abs),
      exists: s.exists,
      mtime: s.mtime,
      size: s.size,
    });
  }
  // Stable ordering: architect, spec, memory (index first then alpha), wiki.
  const order: Record<ContextFile["group"], number> = {
    architect: 0,
    spec: 1,
    memory: 2,
    wiki: 3,
  };
  out.sort((a, b) => {
    if (order[a.group] !== order[b.group]) return order[a.group] - order[b.group];
    if (a.key === "memory_index") return -1;
    if (b.key === "memory_index") return 1;
    return a.label.localeCompare(b.label);
  });
  return out;
}
