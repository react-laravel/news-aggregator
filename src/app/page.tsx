import Link from "next/link";
import { Search } from "lucide-react";
import { BottomNav } from "@/components/site/bottom-nav";
import { NewsCard } from "@/components/site/news-card";
import { NewsFeedFilter } from "@/components/site/news-feed-filter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NEWS_CATEGORIES, DEFAULT_PAGE_SIZE } from "@/lib/constants";
import { prisma } from "@/lib/db";
import { clampPage } from "@/lib/utils";

export const dynamic = "force-dynamic";

type HomeProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function Home({ searchParams }: HomeProps) {
  const params = await searchParams;
  const q = Array.isArray(params.q) ? params.q[0] : params.q;
  const category = Array.isArray(params.category) ? params.category[0] : params.category;
  const page = clampPage(params.page);
  const where = {
    canonicalFor: { isNot: null },
    ...(category && NEWS_CATEGORIES.includes(category as never) ? { category } : {}),
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

  const [articles, total] = await Promise.all([
    prisma.article.findMany({
      where,
      include: { source: true, cluster: true },
      orderBy: [{ publishedAt: "desc" }, { createdAt: "desc" }],
      take: DEFAULT_PAGE_SIZE,
      skip: (page - 1) * DEFAULT_PAGE_SIZE,
    }),
    prisma.article.count({ where }),
  ]);
  const pageCount = Math.max(1, Math.ceil(total / DEFAULT_PAGE_SIZE));

  return (
    <main className="min-h-screen bg-zinc-50 pb-24">
      <div className="mx-auto max-w-5xl px-4 py-5 sm:px-6 md:py-8">
        <header className="mb-5 space-y-4">
          <div>
            <p className="text-sm font-medium text-zinc-500">聚合新闻</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-normal text-zinc-950">今日要闻</h1>
          </div>
          <form className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
              <Input name="q" defaultValue={q} className="pl-9" placeholder="搜索新闻、来源或关键词" />
            </div>
            {category ? <input type="hidden" name="category" value={category} /> : null}
            <Button type="submit">搜索</Button>
          </form>
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <Button variant={!category ? "default" : "outline"} size="sm" className="min-w-14 shrink-0 px-4" asChild>
              <Link href={q ? `/?q=${encodeURIComponent(q)}` : "/"}>全部</Link>
            </Button>
            {NEWS_CATEGORIES.map((item) => (
              <Button key={item} variant={category === item ? "default" : "outline"} size="sm" className="min-w-14 shrink-0 px-4" asChild>
                <Link href={`/?category=${encodeURIComponent(item)}${q ? `&q=${encodeURIComponent(q)}` : ""}`}>{item}</Link>
              </Button>
            ))}
          </div>
        </header>

        {articles.length ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {articles.map((article) => (
              <NewsFeedFilter key={article.id} category={article.category}>
                <NewsCard article={article} />
              </NewsFeedFilter>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center text-zinc-500">
            暂无新闻。请先在后台配置数据源并运行采集任务。
          </div>
        )}

        <div className="mt-6 flex items-center justify-between text-sm text-zinc-500">
          <span>
            第 {page} / {pageCount} 页，共 {total} 条
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} asChild>
              <Link href={`/?page=${page - 1}`}>上一页</Link>
            </Button>
            <Button variant="outline" size="sm" disabled={page >= pageCount} asChild>
              <Link href={`/?page=${page + 1}`}>下一页</Link>
            </Button>
          </div>
        </div>
      </div>
      <BottomNav />
    </main>
  );
}
