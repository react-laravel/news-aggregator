import Link from "next/link";
import { Home, ListChecks } from "lucide-react";

export function BottomNav() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-zinc-200 bg-white/95 backdrop-blur md:hidden">
      <div className="mx-auto grid h-16 max-w-md grid-cols-2">
        <Link className="flex flex-col items-center justify-center gap-1 text-xs text-zinc-600" href="/">
          <Home size={19} />
          首页
        </Link>
        <Link className="flex flex-col items-center justify-center gap-1 text-xs text-zinc-600" href="/categories">
          <ListChecks size={19} />
          订阅
        </Link>
      </div>
    </nav>
  );
}
