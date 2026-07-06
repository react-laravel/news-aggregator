import Link from "next/link";
import { Database, Newspaper, Timer } from "lucide-react";

const links = [
  { href: "/admin/news", label: "新闻", icon: Newspaper },
  { href: "/admin/sources", label: "数据源", icon: Database },
  { href: "/admin/jobs", label: "任务", icon: Timer },
];

export function AdminNav() {
  return (
    <div className="border-b border-zinc-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
        <Link href="/admin/news" className="font-semibold text-zinc-950">
          新闻后台
        </Link>
        <nav className="flex gap-1">
          {links.map((link) => {
            const Icon = link.icon;
            return (
              <Link key={link.href} href={link.href} className="inline-flex items-center gap-1 rounded-md px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-100">
                <Icon size={16} />
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}

