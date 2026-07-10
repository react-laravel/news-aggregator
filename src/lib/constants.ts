export const NEWS_CATEGORIES = ["国内", "国际", "财经", "科技", "AI", "体育", "娱乐", "健康", "汽车"] as const;

export type NewsCategory = (typeof NEWS_CATEGORIES)[number];

export const DEFAULT_PAGE_SIZE = 12;

