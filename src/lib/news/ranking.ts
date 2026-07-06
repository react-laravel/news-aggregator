import type { Article, DataSource } from "@prisma/client";

export function qualityScore(article: {
  summaryZh?: string | null;
  summaryOriginal?: string | null;
  imageUrl?: string | null;
  publishedAt?: Date | null;
}) {
  let score = 0;
  if (article.publishedAt) score += 20;
  if (article.imageUrl) score += 10;
  const summaryLength = (article.summaryZh ?? article.summaryOriginal ?? "").length;
  score += Math.min(30, Math.floor(summaryLength / 8));
  return score;
}

export function chooseCanonical<T extends Article & { source: DataSource }>(articles: T[]) {
  return [...articles].sort((a, b) => {
    if (a.source.priority !== b.source.priority) return a.source.priority - b.source.priority;
    if (a.qualityScore !== b.qualityScore) return b.qualityScore - a.qualityScore;
    return Number(b.publishedAt ?? b.createdAt) - Number(a.publishedAt ?? a.createdAt);
  })[0];
}

