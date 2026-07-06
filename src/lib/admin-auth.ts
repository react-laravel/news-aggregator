import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export const ADMIN_COOKIE = "news_admin_token";

export async function isAdminRequest(request?: NextRequest) {
  const expected = process.env.ADMIN_TOKEN;
  if (!expected) return false;

  if (request) {
    const headerToken = request.headers.get("x-admin-token");
    const cookieToken = request.cookies.get(ADMIN_COOKIE)?.value;
    return headerToken === expected || cookieToken === expected;
  }

  const cookieStore = await cookies();
  return cookieStore.get(ADMIN_COOKIE)?.value === expected;
}

export async function requireAdminPage() {
  if (!(await isAdminRequest())) {
    return false;
  }
  return true;
}

export function unauthorized() {
  return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
}

