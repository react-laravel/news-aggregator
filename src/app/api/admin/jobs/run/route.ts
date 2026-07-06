import { NextRequest, NextResponse } from "next/server";
import { isAdminRequest, unauthorized } from "@/lib/admin-auth";
import { ingestNews } from "@/lib/news/ingest";

export async function POST(request: NextRequest) {
  if (!(await isAdminRequest(request))) return unauthorized();
  try {
    const summary = await ingestNews();
    return NextResponse.json(summary);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 500 });
  }
}

