import { redirect } from "next/navigation";
import { AdminNav } from "@/components/site/admin-nav";
import { SourceCreateForm, SourceRow } from "@/components/site/source-manager";
import { Table, Th } from "@/components/ui/table";
import { prisma } from "@/lib/db";
import { requireAdminPage } from "@/lib/admin-auth";

export const dynamic = "force-dynamic";

export default async function AdminSourcesPage() {
  if (!(await requireAdminPage())) redirect("/admin/login");
  const sources = await prisma.dataSource.findMany({ orderBy: { priority: "asc" } });

  return (
    <main className="min-h-screen bg-zinc-50">
      <AdminNav />
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-5">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal">数据源</h1>
          <p className="mt-1 text-sm text-zinc-500">优先级数字越小越优先，聚合同事件新闻时用于选择展示文章。</p>
        </div>
        <SourceCreateForm />
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <Table>
            <thead>
              <tr>
                <Th>名称</Th>
                <Th>类型</Th>
                <Th>优先级</Th>
                <Th>分类</Th>
                <Th>启用</Th>
                <Th>最近状态</Th>
                <Th>操作</Th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <SourceRow key={source.id} source={source} />
              ))}
            </tbody>
          </Table>
        </div>
      </div>
    </main>
  );
}
