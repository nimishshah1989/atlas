import { NextResponse } from "next/server";
import { readFileSync } from "node:fs";

import { buildAllowlist } from "@/lib/forgeContext";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const MAX_BYTES = 1_000_000; // 1 MB cap — these files are markdown, not blobs.

export async function GET(req: Request) {
  const url = new URL(req.url);
  const key = url.searchParams.get("key");
  if (!key) {
    return NextResponse.json({ error: "missing key" }, { status: 400 });
  }

  // Only keys that the allowlist produced on the server are serveable.
  // The user never supplies a filesystem path.
  const allow = buildAllowlist();
  const entry = allow.get(key);
  if (!entry) {
    return NextResponse.json({ error: "unknown key" }, { status: 404 });
  }

  try {
    const content = readFileSync(entry.abs, "utf8");
    const truncated = content.length > MAX_BYTES;
    return new NextResponse(
      truncated ? content.slice(0, MAX_BYTES) + "\n\n... [truncated]" : content,
      {
        status: 200,
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "no-store",
          "x-file-label": entry.label,
          "x-file-path": entry.abs,
          ...(truncated ? { "x-truncated": "1" } : {}),
        },
      }
    );
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "read failed" },
      { status: 500 }
    );
  }
}
