import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { BottomNav } from "@/components/site/bottom-nav";
import { prisma } from "@/lib/db";
import { formatDateTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function NewsDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const article = await prisma.article.findUnique({
    where: { id },
    include: {
      source: true,
      cluster: {
        include: {
          articles: {
            include: { source: true },
            orderBy: [{ publishedAt: "desc" }, { createdAt: "desc" }],
            take: 8,
          },
        },
      },
    },
  });

  if (!article) notFound();

  return (
    <main className="min-h-screen bg-zinc-50 pb-24">
      <div className="mx-auto max-w-3xl px-4 py-5">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/">
            <ArrowLeft size={16} />
            返回
          </Link>
        </Button>

        <article className="mt-4 space-y-5">
          {article.imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={article.imageUrl} alt="" className="aspect-video w-full rounded-lg object-cover" />
          ) : null}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{article.category}</Badge>
              <span className="text-sm text-zinc-500">{article.sourceName || article.source.name}</span>
              <span className="text-sm text-zinc-400">{formatDateTime(article.publishedAt ?? article.createdAt)}</span>
            </div>
            <h1 className="text-3xl font-semibold leading-tight tracking-normal text-zinc-950">{article.titleZh}</h1>
            <p className="text-base leading-8 text-zinc-700">{article.summaryZh || article.summaryOriginal || "暂无摘要"}</p>
            <Button asChild>
              <a href={article.url} target="_blank" rel="noreferrer">
                阅读原文
                <ExternalLink size={16} />
              </a>
            </Button>
          </div>
        </article>

        {article.cluster?.articles?.length ? (
          <section className="mt-8 space-y-3">
            <h2 className="text-lg font-semibold">同事件来源</h2>
            <div className="space-y-2">
              {article.cluster.articles.map((item) => (
                <Card key={item.id} className="p-3">
                  <a href={item.url} target="_blank" rel="noreferrer" className="block">
                    <div className="text-sm font-medium text-zinc-950">{item.titleZh}</div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {item.sourceName || item.source.name} · {formatDateTime(item.publishedAt ?? item.createdAt)}
                    </div>
                  </a>
                </Card>
              ))}
            </div>
          </section>
        ) : null}
      </div>
      <BottomNav />
    </main>
  );
}

