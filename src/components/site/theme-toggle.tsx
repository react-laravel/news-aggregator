"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";

type Theme = "light" | "dark";

const STORAGE_KEY = "news_theme";

function readTheme(): Theme {
  if (typeof window === "undefined") return "light";
  return window.localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.style.colorScheme = theme;
}

function setTheme(theme: Theme) {
  window.localStorage.setItem(STORAGE_KEY, theme);
  applyTheme(theme);
  window.dispatchEvent(new CustomEvent("news-theme-changed"));
}

function subscribe(callback: () => void) {
  window.addEventListener("news-theme-changed", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("news-theme-changed", callback);
    window.removeEventListener("storage", callback);
  };
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "light");
  const nextTheme = theme === "dark" ? "light" : "dark";
  const Icon = theme === "dark" ? Sun : Moon;

  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      aria-label={theme === "dark" ? "切换浅色模式" : "切换深色模式"}
      title={theme === "dark" ? "浅色模式" : "深色模式"}
      onClick={() => setTheme(nextTheme)}
      className="shrink-0"
    >
      <Icon size={18} />
    </Button>
  );
}

