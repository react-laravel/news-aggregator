"use client";

import { useMemo, useSyncExternalStore } from "react";
import { Check } from "lucide-react";
import { NEWS_CATEGORIES } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "news_subscribed_categories";
const DEFAULT_CATEGORIES: string[] = [...NEWS_CATEGORIES];

let cachedRaw: string | null | undefined;
let cachedCategories: string[] = DEFAULT_CATEGORIES;

export function getStoredCategories() {
  if (typeof window === "undefined") return DEFAULT_CATEGORIES;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === cachedRaw) return cachedCategories;

  cachedRaw = raw;
  if (!raw) {
    cachedCategories = DEFAULT_CATEGORIES;
    return cachedCategories;
  }

  try {
    const parsed = JSON.parse(raw) as string[];
    const valid = parsed.filter((item) => NEWS_CATEGORIES.includes(item as never));
    cachedCategories = valid.length ? valid : DEFAULT_CATEGORIES;
  } catch {
    cachedCategories = DEFAULT_CATEGORIES;
  }
  return cachedCategories;
}

export function setStoredCategories(categories: string[]) {
  const valid = categories.filter((item) => NEWS_CATEGORIES.includes(item as never));
  const next = valid.length ? valid : DEFAULT_CATEGORIES;
  const raw = JSON.stringify(next);
  cachedRaw = raw;
  cachedCategories = next;
  window.localStorage.setItem(STORAGE_KEY, raw);
  window.dispatchEvent(new CustomEvent("news-categories-changed"));
}

export function subscribeToCategoryChanges(callback: () => void) {
  window.addEventListener("news-categories-changed", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("news-categories-changed", callback);
    window.removeEventListener("storage", callback);
  };
}

export function CategoryPreferences() {
  const selected = useSyncExternalStore(subscribeToCategoryChanges, getStoredCategories, () => DEFAULT_CATEGORIES);
  const allSelected = selected.length === NEWS_CATEGORIES.length;

  const summary = useMemo(() => (allSelected ? "全部分类" : selected.join("、")), [allSelected, selected]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-zinc-950">订阅新闻类型</h1>
          <p className="mt-1 text-sm text-zinc-500">当前：{summary}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setStoredCategories(DEFAULT_CATEGORIES)}>
          全选
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {NEWS_CATEGORIES.map((category) => {
          const active = selected.includes(category);
          return (
            <button
              key={category}
              type="button"
              onClick={() =>
                setStoredCategories(
                  selected.includes(category) ? selected.filter((item) => item !== category) : [...selected, category],
                )
              }
              className={cn(
                "flex h-16 items-center justify-between rounded-lg border px-4 text-left text-base font-medium transition",
                active ? "border-zinc-950 bg-zinc-950 text-white" : "border-zinc-200 bg-white text-zinc-800",
              )}
            >
              {category}
              {active ? <Check size={18} /> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}
