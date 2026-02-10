import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Inject API key into requests proxied to the Cairn backend.
 * The rewrite in next.config.ts forwards /api/* to the backend,
 * but doesn't add auth headers — this middleware does.
 */
export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/api/")) {
    const apiKey = process.env.CAIRN_API_KEY;
    if (apiKey) {
      const headers = new Headers(request.headers);
      headers.set("X-API-Key", apiKey);
      return NextResponse.next({ request: { headers } });
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: "/api/:path*",
};
