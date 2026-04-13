import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function proxy(req: NextRequest): NextResponse {
  const expected = process.env.FORGE_SHARE_TOKEN;

  // Dev mode: no token set → open access
  if (!expected) return NextResponse.next();

  const queryToken = req.nextUrl.searchParams.get("token");
  const cookieToken = req.cookies.get("forge_token")?.value;
  const provided = queryToken ?? cookieToken;

  if (provided !== expected) {
    return new NextResponse("Unauthorized", { status: 401 });
  }

  // Token matched. If it came from query param, bake it into a cookie
  // so subsequent requests don't need the query param.
  const response = NextResponse.next();
  if (queryToken !== null) {
    response.cookies.set("forge_token", expected, {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: "/",
    });
  }
  return response;
}

export const config = { matcher: ["/forge/:path*"] };
