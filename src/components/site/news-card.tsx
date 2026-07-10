import Link from "next/link";
import type { Article, DataSource, NewsCluster } from "@prisma/client";
import { ChevronDown } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { NewsImage } from "@/components/site/news-image";
import { formatDateTime } from "@/lib/utils";

type NewsCardArticle = Article & {
  source: DataSource;
  cluster?: NewsCluster | null;
};

function collectionMethodLabel(type: DataSource["type"]) {
  switch (type) {
    case "brave_news":
      return "Brave 新闻搜索";
    case "google_cse":
      return "Google 自定义搜索";
    case "openai_web_search":
      return "OpenAI 联网搜索";
    case "crawler":
      return "RSS 订阅";
  }
}

export function NewsCard({ article }: { article: NewsCardArticle }) {
  const sourceName = article.sourceName || article.source.name;
  const collectionMethod = collectionMethodLabel(article.source.type);

  return (
    <Card className="overflow-hidden transition hover:border-zinc-300 hover:shadow-md dark:hover:border-zinc-700">
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{article.category}</Badge>
          {sourceName !== article.source.name ? (
            <span className="text-xs text-zinc-500 dark:text-zinc-400">{article.sourceName || article.source.name}</span>
          ) : null}
          <span className="text-xs text-zinc-500 dark:text-zinc-400">采集：{collectionMethod}</span>
          <span className="text-xs text-zinc-400 dark:text-zinc-500">{formatDateTime(article.publishedAt ?? article.createdAt)}</span>
        </div>
        <Link href={`/news/${article.id}`} className="block space-y-3">
          <h2 className="text-lg font-semibold leading-snug text-zinc-950 dark:text-zinc-50">{article.titleZh}</h2>
          <p className="line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{article.summaryZh || article.summaryOriginal || "暂无摘要"}</p>
        </Link>
      </div>

      {article.imageUrl ? (
        <details className="group/image border-t border-zinc-200 dark:border-zinc-800">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-2.5 text-xs font-medium text-zinc-500 transition hover:bg-zinc-50 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800/60 dark:hover:text-zinc-200 [&::-webkit-details-marker]:hidden">
            <span className="group-open/image:hidden">展开图片</span>
            <span className="hidden group-open/image:inline">收起图片</span>
            <ChevronDown className="h-4 w-4 transition-transform group-open/image:rotate-180" />
          </summary>
          <NewsImage
            src={article.imageUrl}
            sizes="(max-width: 767px) 100vw, (max-width: 1023px) 50vw, 33vw"
            className="h-48 w-full border-t border-zinc-200 dark:border-zinc-800"
          />
        </details>
      ) : null}
    </Card>
  );
}
