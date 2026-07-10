import { NextRequest, NextResponse } from "next/server";
import { ADMIN_COOKIE } from "@/lib/admin-constants";

const ALLOWED_PATHS = new Set(["/admin/login", "/api/admin/session"]);

function hasAdminToken(request: NextRequest) {
  const expected = process.env.ADMIN_TOKEN;
  if (!expected) return false;

  const headerToken = request.headers.get("x-admin-token");
  const cookieToken = request.cookies.get(ADMIN_COOKIE)?.value;

  return headerToken === expected || cookieToken === expected;
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (ALLOWED_PATHS.has(pathname) || hasAdminToken(request)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/admin/login";
  loginUrl.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\.(?:png|jpg|jpeg|gif|webp|svg|ico|css|js|map|txt|xml|woff|woff2)$).*)",
  ],
};
