import { NextResponse } from "next/server";
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { listContextFiles } from "@/lib/forgeContext";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const REPO_ROOT = path.resolve(process.cwd(), "..");
const STATE_DB = path.join(REPO_ROOT, "orchestrator", "state.db");
const REPORT_JSON = path.join(REPO_ROOT, ".quality", "report.json");
const LOGS_DIR = path.join(REPO_ROOT, "orchestrator", "logs");

type Chunk = {
  id: string;
  title: string;
  status: string;
  attempts: number;
  last_error: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};

function readChunks(): Chunk[] {
  try {
    const raw = execFileSync(
      "sqlite3",
      [
        "-readonly",
        "-json",
        STATE_DB,
        "SELECT id, title, status, attempts, last_error, started_at, finished_at, updated_at FROM chunks ORDER BY id;",
      ],
      { encoding: "utf8", timeout: 5000 }
    );
    return raw ? (JSON.parse(raw) as Chunk[]) : [];
  } catch {
    return [];
  }
}

function readReport(): Record<string, unknown> | null {
  try {
    return JSON.parse(readFileSync(REPORT_JSON, "utf8"));
  } catch {
    return null;
  }
}

function tailFile(p: string, lines = 60): string[] {
  try {
    const txt = readFileSync(p, "utf8").trimEnd();
    if (!txt) return [];
    return txt.split("\n").slice(-lines);
  } catch {
    return [];
  }
}

function latestLog(): { name: string; tail: string[]; mtime: string } | null {
  try {
    const files = readdirSync(LOGS_DIR)
      .filter((f) => f.endsWith(".log"))
      .map((f) => {
        const full = path.join(LOGS_DIR, f);
        return { name: f, full, mtime: statSync(full).mtimeMs };
      })
      .sort((a, b) => b.mtime - a.mtime);
    if (files.length === 0) return null;
    const top = files[0];
    return {
      name: top.name,
      tail: tailFile(top.full, 80),
      mtime: new Date(top.mtime).toISOString(),
    };
  } catch {
    return null;
  }
}

export async function GET() {
  return NextResponse.json(
    {
      now: new Date().toISOString(),
      chunks: readChunks(),
      quality: readReport(),
      log: latestLog(),
      context: listContextFiles(),
    },
    { headers: { "cache-control": "no-store" } }
  );
}
