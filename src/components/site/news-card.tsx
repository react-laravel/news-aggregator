import Link from "next/link";
import type { Article, DataSource, NewsCluster } from "@prisma/client";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { formatDateTime } from "@/lib/utils";

type NewsCardArticle = Article & {
  source: DataSource;
  cluster?: NewsCluster | null;
};

export function NewsCard({ article }: { article: NewsCardArticle }) {
  return (
    <Link href={`/news/${article.id}`} className="block">
      <Card className="overflow-hidden transition hover:border-zinc-300 hover:shadow-md">
        {article.imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={article.imageUrl} alt="" className="h-40 w-full object-cover" loading="lazy" />
        ) : null}
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{article.category}</Badge>
            <span className="text-xs text-zinc-500">{article.sourceName || article.source.name}</span>
            <span className="text-xs text-zinc-400">{formatDateTime(article.publishedAt ?? article.createdAt)}</span>
          </div>
          <h2 className="line-clamp-2 text-lg font-semibold leading-snug text-zinc-950">{article.titleZh}</h2>
          <p className="line-clamp-3 text-sm leading-6 text-zinc-600">{article.summaryZh || article.summaryOriginal || "暂无摘要"}</p>
        </div>
      </Card>
    </Link>
  );
}

