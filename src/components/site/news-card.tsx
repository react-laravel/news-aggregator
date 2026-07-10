import type { Article, DataSource, NewsCluster } from "@prisma/client";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
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
    <a href={article.url} target="_blank" rel="noreferrer" className="block">
      <Card className="h-full transition hover:border-zinc-300 hover:shadow-md dark:hover:border-zinc-700">
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{article.category}</Badge>
            {sourceName !== article.source.name ? (
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{sourceName}</span>
            ) : null}
            <span className="text-xs text-zinc-500 dark:text-zinc-400">采集：{collectionMethod}</span>
            <span className="text-xs text-zinc-400 dark:text-zinc-500">{formatDateTime(article.publishedAt ?? article.createdAt)}</span>
          </div>
          <h2 className="text-lg font-semibold leading-snug text-zinc-950 dark:text-zinc-50">{article.titleZh}</h2>
        </div>
      </Card>
    </a>
  );
}
