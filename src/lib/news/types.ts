import type { DataSource } from "@prisma/client";

export type CandidateArticle = {
  url: string;
  sourceName: string;
  titleOriginal: string;
  summaryOriginal?: string | null;
  language?: string;
  category: string;
  publishedAt?: Date | null;
  raw?: unknown;
};

export type NewsAdapter = {
  fetch(source: DataSource): Promise<CandidateArticle[]>;
};
