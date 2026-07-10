import Link from "next/link";
import { BarChart3, Home, ListChecks } from "lucide-react";

export function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-zinc-200 bg-white/95 backdrop-blur md:hidden dark:border-zinc-800 dark:bg-zinc-950/95">
      <div className="mx-auto grid h-16 max-w-md grid-cols-3">
        <Link className="flex flex-col items-center justify-center gap-1 text-xs text-zinc-600 dark:text-zinc-300" href="/">
          <Home size={19} />
          首页
        </Link>
        <Link className="flex flex-col items-center justify-center gap-1 text-xs text-zinc-600 dark:text-zinc-300" href="/categories">
          <ListChecks size={19} />
          订阅
        </Link>
        <Link className="flex flex-col items-center justify-center gap-1 text-xs text-zinc-600 dark:text-zinc-300" href="/stats">
          <BarChart3 size={19} />
          统计
        </Link>
      </div>
    </nav>
  );
}
