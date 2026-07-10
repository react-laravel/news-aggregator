import type { DataSource } from "@prisma/client";
import { NEWS_CATEGORIES } from "@/lib/constants";
import type { NewsAdapter } from "../types";

type OpenAINewsResult = {
  title: string;
  url: string;
  sourceName?: string;
  summary?: string;
  category?: string;
  publishedAt?: string;
};

export const openaiWebSearchAdapter: NewsAdapter = {
  async fetch(source: DataSource) {
    if (!process.env.OPENAI_API_KEY) return [];
    const categories = source.categoryKeys.length ? source.categoryKeys : [...NEWS_CATEGORIES];
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "gpt-5-mini",
        tools: [{ type: "web_search" }],
        input: `搜索最近一小时到一天内的中文或英文重要新闻，分类限定在：${categories.join("、")}。返回最多20条，英文新闻的标题和摘要也用中文概括，但保留原始URL。`,
        text: {
          format: {
            type: "json_schema",
            name: "news_results",
            schema: {
              type: "object",
              additionalProperties: false,
              required: ["items"],
              properties: {
                items: {
                  type: "array",
                  items: {
                    type: "object",
                    additionalProperties: false,
                    required: ["title", "url", "summary", "category"],
                    properties: {
                      title: { type: "string" },
                      url: { type: "string" },
                      sourceName: { type: "string" },
                      summary: { type: "string" },
                      category: { type: "string" },
                      publishedAt: { type: "string" },
                    },
                  },
                },
              },
            },
          },
        },
      }),
    });

    if (!response.ok) throw new Error(`OpenAI web search failed: ${response.status}`);
    const data = (await response.json()) as { output_text?: string };
    const parsed = JSON.parse(data.output_text ?? "{\"items\":[]}") as { items?: OpenAINewsResult[] };

    return (parsed.items ?? [])
      .filter((item) => item.url && item.title)
      .map((item) => ({
        url: item.url,
        sourceName: item.sourceName || source.name,
        titleOriginal: item.title,
        summaryOriginal: item.summary,
        titleZh: item.title,
        summaryZh: item.summary,
        category: categories.includes(item.category as never) ? item.category! : categories[0]!,
        publishedAt: item.publishedAt ? new Date(item.publishedAt) : null,
        raw: item,
      }));
  },
};
