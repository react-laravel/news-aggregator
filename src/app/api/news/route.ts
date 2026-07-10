import { NextRequest, NextResponse } from "next/server";
import { NEWS_CATEGORIES, DEFAULT_PAGE_SIZE } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { clampPage } from "@/lib/utils";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const page = clampPage(request.nextUrl.searchParams.get("page") ?? undefined);
  const q = request.nextUrl.searchParams.get("q") ?? undefined;
  const category = request.nextUrl.searchParams.get("category") ?? undefined;
  const where = {
    canonicalFor: { isNot: null },
    ...(category && NEWS_CATEGORIES.includes(category as never) ? { category } : {}),
    ...(q
      ? {
          OR: [
            { titleZh: { contains: q, mode: "insensitive" as const } },
            { sourceName: { contains: q, mode: "insensitive" as const } },
          ],
        }
      : {}),
  };
  const [articles, total] = await Promise.all([
    prisma.article.findMany({
      where,
      include: { source: true },
      orderBy: [{ publishedAt: "desc" }, { createdAt: "desc" }],
      take: DEFAULT_PAGE_SIZE,
      skip: (page - 1) * DEFAULT_PAGE_SIZE,
    }),
    prisma.article.count({ where }),
  ]);

  return NextResponse.json({ articles, total, page });
}
