import { redirect } from "next/navigation";
import { AdminNav } from "@/components/site/admin-nav";
import { SourceCard, SourceCreateForm } from "@/components/site/source-manager";
import { prisma } from "@/lib/db";
import { requireAdminPage } from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

export default async function AdminSourcesPage() {
  if (!(await requireAdminPage())) redirect("/admin/login");
  const sources = await prisma.dataSource.findMany({ orderBy: { priority: "asc" } });

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <AdminNav />
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-zinc-950 dark:text-zinc-50">数据源</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">优先级数字越小越优先，聚合同事件新闻时用于选择展示文章。</p>
        </div>
        <SourceCreateForm />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sources.map((source) => (
            <SourceCard key={source.id} source={source} />
          ))}
        </div>
      </div>
    </main>
  );
}
