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
    <div className="bg-white shadow-sm dark:border-b dark:border-zinc-800 dark:bg-zinc-950 dark:shadow-none">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-3">
        <Link href="/admin/news" className="shrink-0 text-base font-semibold text-zinc-950 dark:text-zinc-50">
          新闻后台
        </Link>
        <nav className="flex min-w-0 items-center justify-end gap-1">
          {links.map((link) => {
            const Icon = link.icon;
            return (
              <Link
                key={link.href}
                href={link.href}
                className="inline-flex h-10 min-w-10 items-center justify-center gap-1 rounded-md px-2 text-sm text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800 sm:px-3"
                title={link.label}
              >
                <Icon size={16} className="shrink-0" />
                <span className="hidden sm:inline">{link.label}</span>
              </Link>
            );
          })}
          <ThemeToggle />
        </nav>
      </div>
    </div>
  );
}
