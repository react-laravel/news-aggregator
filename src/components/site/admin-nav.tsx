import Link from "next/link";
import { Database, Newspaper, Timer } from "lucide-react";
import { ThemeToggle } from "@/components/site/theme-toggle";

const links = [
  { href: "/admin/news", label: "新闻", icon: Newspaper },
  { href: "/admin/sources", label: "数据源", icon: Database },
  { href: "/admin/jobs", label: "任务", icon: Timer },
];

export function AdminNav() {
  return (
    <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <Link href="/admin/news" className="text-lg font-semibold text-zinc-950 dark:text-zinc-50 sm:text-base">
          新闻后台
        </Link>
        <nav className="grid w-full grid-cols-4 gap-1 sm:w-auto sm:flex sm:items-center">
          {links.map((link) => {
            const Icon = link.icon;
            return (
              <Link
                key={link.href}
                href={link.href}
                className="inline-flex min-w-0 items-center justify-center gap-1 rounded-md px-2 py-2 text-sm text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 sm:px-3"
              >
                <Icon size={16} className="shrink-0" />
                <span className="truncate">{link.label}</span>
              </Link>
            );
          })}
          <ThemeToggle />
        </nav>
      </div>
    </div>
  );
}
