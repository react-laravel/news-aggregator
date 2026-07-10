import { describe, expect, it } from "vitest";
import { categoryFromText, detectLanguage, normalizeUrl, titleSimilarity } from "./normalize";

describe("news normalization", () => {
  it("removes tracking params and normalizes host", () => {
    expect(normalizeUrl("https://www.Example.com/a/?utm_source=x&b=2#top")).toBe("https://example.com/a/?b=2");
  });

  it("scores similar titles", () => {
    expect(titleSimilarity("OpenAI releases a new AI model", "OpenAI releases new model")).toBeGreaterThan(0.5);
  });

  it("detects language from cjk density", () => {
    expect(detectLanguage("今日科技新闻", "人工智能公司发布新产品")).toBe("zh");
    expect(detectLanguage("OpenAI releases new model", "Developers get updated API tools")).toBe("en");
  });

  it("maps text to category", () => {
    expect(categoryFromText("OpenAI 发布新的大模型")).toBe("AI");
    expect(categoryFromText("新能源汽车销量增长")).toBe("汽车");
  });
});

