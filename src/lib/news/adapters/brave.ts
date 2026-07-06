import type { DataSource } from "@prisma/client";
import { NEWS_CATEGORIES } from "@/lib/constants";
import { categoryFromText } from "../normalize";
import type { CandidateArticle, NewsAdapter } from "../types";

type BraveNewsResponse = {
  results?: Array<{
    title?: string;
    url?: string;
    description?: string;
    age?: string;
    page_age?: string;
    source?: string;
    thumbnail?: { src?: string };
  }>;
};

export const braveNewsAdapter: NewsAdapter = {
  async fetch(source: DataSource) {
    const apiKey = process.env.BRAVE_SEARCH_API_KEY;
    if (!apiKey) return [];
    const categories = source.categoryKeys.length ? source.categoryKeys : [...NEWS_CATEGORIES];
    const articles: CandidateArticle[] = [];

    for (const category of categories) {
      const query = source.query || `${category} 新闻`;
      const url = new URL("https://api.search.brave.com/res/v1/news/search");
      url.searchParams.set("q", query.includes(category) ? query : `${query} ${category}`);
      url.searchParams.set("count", "10");
      url.searchParams.set("freshness", "pd");

      const response = await fetch(url, {
        headers: {
          Accept: "application/json",
          "X-Subscription-Token": apiKey,
        },
      });
      if (!response.ok) throw new Error(`Brave news failed: ${response.status}`);
      const data = (await response.json()) as BraveNewsResponse;
      for (const result of data.results ?? []) {
        if (!result.url || !result.title) continue;
        articles.push({
          url: result.url,
          sourceName: result.source || source.name,
          titleOriginal: result.title,
          summaryOriginal: result.description,
          category: categoryFromText(`${result.title} ${result.description ?? ""}`, category),
          imageUrl: result.thumbnail?.src,
          publishedAt: result.page_age ? new Date(result.page_age) : null,
          raw: result,
        });
      }
    }

    return articles;
  },
};

