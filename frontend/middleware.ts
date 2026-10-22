import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/login") return NextResponse.next();
  return NextResponse.next();
}

export const config = { matcher: ["/knowledge/:path*", "/agent/:path*", "/dashboard/:path*", "/admin/:path*"] };
