import { SourceType } from "@prisma/client";
import type { NewsAdapter } from "../types";
import { braveNewsAdapter } from "./brave";
import { crawlerAdapter } from "./crawler";
import { googleCseAdapter } from "./google";
import { openaiWebSearchAdapter } from "./openai";

export const adapters: Record<SourceType, NewsAdapter> = {
  crawler: crawlerAdapter,
  brave_news: braveNewsAdapter,
  google_cse: googleCseAdapter,
  openai_web_search: openaiWebSearchAdapter,
};

