/**
 * Thin proxy to ATLAS backend system endpoints.
 * Zero fs imports — backend owns all filesystem reads.
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BACKEND_BASE = "http://localhost:8010/api/v1/system";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const { searchParams } = req.nextUrl;
  const path = searchParams.get("path") ?? "heartbeat";

  // Allowlist of backend sub-paths to forward
  const allowed = new Set([
    "heartbeat",
    "roadmap",
    "quality",
    "logs/tail",
  ]);

  if (!allowed.has(path)) {
    return NextResponse.json({ error: "unknown path" }, { status: 400 });
  }

  // Forward any query params (e.g., lines=N for logs/tail)
  const forwardParams = new URLSearchParams(searchParams);
  forwardParams.delete("path");
  const qs = forwardParams.toString();
  const url = `${BACKEND_BASE}/${path}${qs ? `?${qs}` : ""}`;

  try {
    const upstream = await fetch(url, { cache: "no-store" });
    const body = await upstream.text();
    return new NextResponse(body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "upstream error";
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
