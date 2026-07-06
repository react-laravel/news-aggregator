"use client";

import { useSyncExternalStore } from "react";
import { getStoredCategories, subscribeToCategoryChanges } from "./category-preferences";

export function NewsFeedFilter({ children, category }: { children: React.ReactNode; category: string }) {
  const selected = useSyncExternalStore(subscribeToCategoryChanges, getStoredCategories, () => []);
  const visible = selected.includes(category);

  if (!visible) return null;
  return children;
}
