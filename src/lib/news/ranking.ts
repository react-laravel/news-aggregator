import type { Article, DataSource } from "@prisma/client";

export function qualityScore(article: {
  publishedAt?: Date | null;
}) {
  return article.publishedAt ? 20 : 0;
}

export function chooseCanonical<T extends Article & { source: DataSource }>(articles: T[]) {
  return [...articles].sort((a, b) => {
    if (a.source.priority !== b.source.priority) return a.source.priority - b.source.priority;
    if (a.qualityScore !== b.qualityScore) return b.qualityScore - a.qualityScore;
    return Number(b.publishedAt ?? b.createdAt) - Number(a.publishedAt ?? a.createdAt);
  })[0];
}
