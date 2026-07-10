import type { DataSource } from "@prisma/client";
import { ProxyAgent, setGlobalDispatcher } from "undici";
import { NEWS_CATEGORIES } from "@/lib/constants";
import { categoryFromText, normalizeTitle } from "../normalize";
import type { CandidateArticle, NewsAdapter } from "../types";


let proxyConfigured = false;
function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function configureProxy() {
  if (proxyConfigured) return;
  proxyConfigured = true;
  const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy || process.env.HTTP_PROXY || process.env.http_proxy;
  if (proxyUrl) {
    setGlobalDispatcher(new ProxyAgent(proxyUrl));
  }
}

type BraveNewsResponse = {
  results?: Array<{
    title?: string;
    url?: string;
    description?: string;
    age?: string;
    page_age?: string;
    meta_url?: {
      hostname?: string;
    };
  }>;
};

export const braveNewsAdapter: NewsAdapter = {
  async fetch(source: DataSource) {
    configureProxy();
    const apiKey = process.env.BRAVE_SEARCH_API_KEY;
    if (!apiKey) return [];
    const categories = source.categoryKeys.length ? source.categoryKeys : [...NEWS_CATEGORIES];
    const articles: CandidateArticle[] = [];
    const seenResults = new Set<string>();

    for (const category of categories) {
      const query = source.query || `${category} 新闻`;
      const url = new URL("https://api.search.brave.com/res/v1/news/search");
      url.searchParams.set("q", query.includes(category) ? query : `${query} ${category}`);
      url.searchParams.set("count", "5");
      url.searchParams.set("freshness", "pd");

      let response = await fetch(url, {
        headers: {
          Accept: "application/json",
          "X-Subscription-Token": apiKey,
        },
      });
      if (response.status === 429) {
        await sleep(2500);
        response = await fetch(url, {
          headers: {
            Accept: "application/json",
            "X-Subscription-Token": apiKey,
          },
        });
      }
      if (!response.ok) throw new Error(`Brave news failed: ${response.status}`);
      const data = (await response.json()) as BraveNewsResponse;
      await sleep(1200);
      for (const result of data.results ?? []) {
        if (!result.url || !result.title) continue;
        const hostname = result.meta_url?.hostname || new URL(result.url).hostname.replace(/^www\./, "");
        const resultKey = `${hostname}:${normalizeTitle(result.title)}`;
        if (seenResults.has(resultKey)) continue;
        seenResults.add(resultKey);

        articles.push({
          url: result.url,
          sourceName: hostname || source.name,
          titleOriginal: result.title,
          summaryOriginal: result.description,
          category: categoryFromText(result.title, category),
          publishedAt: result.page_age ? new Date(result.page_age) : null,
          raw: result,
        });
      }
    }

    return articles;
  },
};
