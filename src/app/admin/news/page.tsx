import Link from "next/link";
import { redirect } from "next/navigation";
import { AdminNav } from "@/components/site/admin-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { NEWS_CATEGORIES, DEFAULT_PAGE_SIZE } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { requireAdminPage } from "@/lib/admin-auth";
import { clampPage, formatDateTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function AdminNewsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  if (!(await requireAdminPage())) redirect("/admin/login");
  const params = await searchParams;
  const page = clampPage(params.page);
  const q = Array.isArray(params.q) ? params.q[0] : params.q;
  const category = Array.isArray(params.category) ? params.category[0] : params.category;
  const sourceId = Array.isArray(params.sourceId) ? params.sourceId[0] : params.sourceId;
  const where = {
    ...(category ? { category } : {}),
    ...(sourceId ? { sourceId } : {}),
    ...(q
      ? {
          OR: [
            { titleZh: { contains: q, mode: "insensitive" as const } },
            { summaryZh: { contains: q, mode: "insensitive" as const } },
            { sourceName: { contains: q, mode: "insensitive" as const } },
          ],
        }
      : {}),
  };
  const [articles, total, sources] = await Promise.all([
    prisma.article.findMany({
      where,
      include: { source: true, canonicalFor: true },
      orderBy: [{ publishedAt: "desc" }, { createdAt: "desc" }],
      take: DEFAULT_PAGE_SIZE,
      skip: (page - 1) * DEFAULT_PAGE_SIZE,
    }),
    prisma.article.count({ where }),
    prisma.dataSource.findMany({ orderBy: { priority: "asc" } }),
  ]);
  const pageCount = Math.max(1, Math.ceil(total / DEFAULT_PAGE_SIZE));
  const pageHref = (nextPage: number) => {
    const nextParams = new URLSearchParams();
    nextParams.set("page", String(nextPage));
    if (q) nextParams.set("q", q);
    if (category) nextParams.set("category", category);
    if (sourceId) nextParams.set("sourceId", sourceId);
    return `/admin/news?${nextParams.toString()}`;
  };

  return (
    <main className="min-h-screen overflow-x-hidden bg-zinc-50 dark:bg-zinc-950">
      <AdminNav />
      <div className="mx-auto w-full max-w-6xl space-y-4 px-4 py-5">
        <form className="grid gap-2 rounded-lg border border-zinc-200 bg-white p-3 md:grid-cols-[1fr_160px_180px_auto] dark:border-zinc-800 dark:bg-zinc-900">
          <Input name="q" defaultValue={q} placeholder="搜索标题、摘要、来源" />
          <Select name="category" defaultValue={category ?? ""}>
            <option value="">全部分类</option>
            {NEWS_CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
          <Select name="sourceId" defaultValue={sourceId ?? ""}>
            <option value="">全部来源</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.name}
              </option>
            ))}
          </Select>
          <Button type="submit">筛选</Button>
        </form>

        <div className="grid min-w-0 gap-3 lg:grid-cols-2">
          {articles.map((article) => (
            <article key={article.id} className="min-w-0 space-y-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <div className="flex items-start justify-between gap-3">
                <Badge>{article.category}</Badge>
                {article.canonicalFor ? <Badge>展示中</Badge> : <span className="shrink-0 text-xs text-zinc-400 dark:text-zinc-500">聚合隐藏</span>}
              </div>
              <div className="min-w-0 space-y-2">
                <Link href={`/news/${article.id}`} className="block text-base font-semibold leading-snug text-zinc-950 hover:underline dark:text-zinc-50">
                  {article.titleZh}
                </Link>
                <p className="line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{article.summaryZh || article.summaryOriginal || "暂无摘要"}</p>
              </div>
              <dl className="grid grid-cols-2 gap-3 text-sm">
                <div className="min-w-0">
                  <dt className="text-xs text-zinc-500 dark:text-zinc-400">来源</dt>
                  <dd className="mt-1 break-words text-zinc-800 dark:text-zinc-200">{article.sourceName || article.source.name}</dd>
                </div>
                <div className="min-w-0">
                  <dt className="text-xs text-zinc-500 dark:text-zinc-400">时间</dt>
                  <dd className="mt-1 text-zinc-800 dark:text-zinc-200">{formatDateTime(article.publishedAt ?? article.createdAt)}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>

        <div className="flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
          <span>
            第 {page} / {pageCount} 页，共 {total} 条
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} asChild>
              <Link href={pageHref(page - 1)}>上一页</Link>
            </Button>
            <Button variant="outline" size="sm" disabled={page >= pageCount} asChild>
              <Link href={pageHref(page + 1)}>下一页</Link>
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}
