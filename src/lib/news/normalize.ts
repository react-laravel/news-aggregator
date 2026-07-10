const TRACKING_PARAMS = new Set([
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "fbclid",
  "gclid",
  "yclid",
  "igshid",
]);

const STOP_WORDS = new Set(["the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "from"]);

export function normalizeUrl(value: string) {
  const parsed = new URL(value);
  parsed.hash = "";
  parsed.protocol = parsed.protocol.toLowerCase();
  parsed.hostname = parsed.hostname.replace(/^www\./, "").toLowerCase();
  for (const key of [...parsed.searchParams.keys()]) {
    if (TRACKING_PARAMS.has(key.toLowerCase())) {
      parsed.searchParams.delete(key);
    }
  }
  parsed.searchParams.sort();
  const output = parsed.toString();
  return output.endsWith("/") ? output.slice(0, -1) : output;
}

export function normalizeTitle(title: string) {
  return title
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((part) => part && !STOP_WORDS.has(part))
    .join(" ")
    .trim();
}

export function titleSimilarity(a: string, b: string) {
  const aTokens = new Set(normalizeTitle(a).split(/\s+/).filter(Boolean));
  const bTokens = new Set(normalizeTitle(b).split(/\s+/).filter(Boolean));
  if (aTokens.size === 0 || bTokens.size === 0) return 0;
  let intersection = 0;
  for (const token of aTokens) {
    if (bTokens.has(token)) intersection += 1;
  }
  return intersection / (aTokens.size + bTokens.size - intersection);
}

export function clusterFingerprint(title: string, category: string) {
  const normalized = normalizeTitle(title);
  const core = normalized
    .split(/\s+/)
    .slice(0, 12)
    .join("-");
  return `${category}:${core || "untitled"}`;
}

export function detectLanguage(title: string, summary?: string | null) {
  const text = `${title} ${summary ?? ""}`;
  const cjk = (text.match(/[\u3400-\u9fff]/g) ?? []).length;
  const latin = (text.match(/[a-zA-Z]/g) ?? []).length;
  return cjk >= latin * 0.25 ? "zh" : "en";
}

export function categoryFromText(text: string, fallback = "国内") {
  const content = text.toLowerCase();
  const checks: Array<[string, RegExp]> = [
    ["AI", /\b(ai|人工智能|openai|模型|大模型|机器人)\b/i],
    ["科技", /科技|芯片|软件|手机|互联网|计算机|semiconductor|technology/i],
    ["财经", /财经|股票|基金|市场|经济|投资|finance|market|stock/i],
    ["体育", /体育|足球|篮球|比赛|冠军|sport|nba|football/i],
    ["娱乐", /娱乐|电影|音乐|明星|演出|celebrity|movie|music/i],
    ["健康", /健康|医疗|医院|药物|疾病|health|medical/i],
    ["汽车", /汽车|新能源车|电动车|auto|vehicle|tesla/i],
    ["国际", /国际|美国|欧洲|日本|韩国|全球|world|global|foreign/i],
  ];
  return checks.find(([, pattern]) => pattern.test(content))?.[0] ?? fallback;
}

