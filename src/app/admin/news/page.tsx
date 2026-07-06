import Link from "next/link";
import { redirect } from "next/navigation";
import { AdminNav } from "@/components/site/admin-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, Td, Th } from "@/components/ui/table";
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

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <AdminNav />
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-5">
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

        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <Table>
            <thead>
              <tr>
                <Th>新闻</Th>
                <Th>分类</Th>
                <Th>来源</Th>
                <Th>时间</Th>
                <Th>状态</Th>
              </tr>
            </thead>
            <tbody>
              {articles.map((article) => (
                <tr key={article.id}>
                  <Td className="min-w-80">
                    <Link href={`/news/${article.id}`} className="font-medium text-zinc-950 hover:underline dark:text-zinc-50">
                      {article.titleZh}
                    </Link>
                    <div className="mt-1 line-clamp-2 text-xs text-zinc-500 dark:text-zinc-400">{article.summaryZh || article.summaryOriginal}</div>
                  </Td>
                  <Td>{article.category}</Td>
                  <Td>{article.sourceName || article.source.name}</Td>
                  <Td>{formatDateTime(article.publishedAt ?? article.createdAt)}</Td>
                  <Td>{article.canonicalFor ? <Badge>展示中</Badge> : <span className="text-zinc-400 dark:text-zinc-500">聚合隐藏</span>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>

        <div className="flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
          <span>
            第 {page} / {pageCount} 页，共 {total} 条
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} asChild>
              <Link href={`/admin/news?page=${page - 1}`}>上一页</Link>
            </Button>
            <Button variant="outline" size="sm" disabled={page >= pageCount} asChild>
              <Link href={`/admin/news?page=${page + 1}`}>下一页</Link>
            </Button>
          </div>
        </div>
      </div>
    </main>
  );
}
