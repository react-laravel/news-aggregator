import type { DataSource } from "@prisma/client";
import Parser from "rss-parser";
import { htmlToText } from "html-to-text";
import { categoryFromText } from "../normalize";
import type { CandidateArticle, NewsAdapter } from "../types";

const parser = new Parser();

export const crawlerAdapter: NewsAdapter = {
  async fetch(source: DataSource) {
    if (!source.baseUrl) return [];
    const feed = await parser.parseURL(source.baseUrl);
    return feed.items.slice(0, 30).map((item): CandidateArticle => {
      const title = item.title ?? "无标题";
      const summary = htmlToText(item.contentSnippet ?? item.content ?? "", {
        wordwrap: false,
        selectors: [{ selector: "a", options: { ignoreHref: true } }],
      }).slice(0, 500);
      const category = categoryFromText(`${title} ${summary}`, source.categoryKeys[0] ?? "国内");

      return {
        url: item.link ?? source.baseUrl ?? "",
        sourceName: feed.title ?? source.name,
        titleOriginal: title,
        summaryOriginal: summary,
        category,
        publishedAt: item.isoDate ? new Date(item.isoDate) : null,
        raw: item,
      };
    }).filter((article) => article.url);
  },
};

