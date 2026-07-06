import type { DataSource } from "@prisma/client";
import { NEWS_CATEGORIES } from "@/lib/constants";
import { categoryFromText } from "../normalize";
import type { CandidateArticle, NewsAdapter } from "../types";

type GoogleSearchResponse = {
  items?: Array<{
    title?: string;
    link?: string;
    snippet?: string;
    pagemap?: {
      cse_image?: Array<{ src?: string }>;
      metatags?: Array<{ ["article:published_time"]?: string; ["og:site_name"]?: string }>;
    };
  }>;
};

export const googleCseAdapter: NewsAdapter = {
  async fetch(source: DataSource) {
    const key = process.env.GOOGLE_API_KEY;
    const cx = process.env.GOOGLE_CSE_ID;
    if (!key || !cx) return [];

    const categories = source.categoryKeys.length ? source.categoryKeys : [...NEWS_CATEGORIES];
    const articles: CandidateArticle[] = [];
    for (const category of categories) {
      const url = new URL("https://www.googleapis.com/customsearch/v1");
      url.searchParams.set("key", key);
      url.searchParams.set("cx", cx);
      url.searchParams.set("q", `${source.query || category} 新闻`);
      url.searchParams.set("num", "10");
      url.searchParams.set("sort", "date");

      const response = await fetch(url);
      if (!response.ok) throw new Error(`Google CSE failed: ${response.status}`);
      const data = (await response.json()) as GoogleSearchResponse;
      for (const item of data.items ?? []) {
        if (!item.link || !item.title) continue;
        const meta = item.pagemap?.metatags?.[0];
        articles.push({
          url: item.link,
          sourceName: meta?.["og:site_name"] || source.name,
          titleOriginal: item.title,
          summaryOriginal: item.snippet,
          category: categoryFromText(`${item.title} ${item.snippet ?? ""}`, category),
          imageUrl: item.pagemap?.cse_image?.[0]?.src,
          publishedAt: meta?.["article:published_time"] ? new Date(meta["article:published_time"]) : null,
          raw: item,
        });
      }
    }
    return articles;
  },
};

