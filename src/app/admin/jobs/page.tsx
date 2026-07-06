import { redirect } from "next/navigation";
import { AdminNav } from "@/components/site/admin-nav";
import { JobRunner } from "@/components/site/job-runner";
import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import { prisma } from "@/lib/db";
import { requireAdminPage } from "@/lib/admin-auth";
import { formatDateTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export default async function AdminJobsPage() {
  if (!(await requireAdminPage())) redirect("/admin/login");
  const jobs = await prisma.ingestJob.findMany({ orderBy: { startedAt: "desc" }, take: 30 });

  return (
    <main className="min-h-screen bg-zinc-50">
      <AdminNav />
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal">采集任务</h1>
            <p className="mt-1 text-sm text-zinc-500">Linux 部署后建议用 systemd timer 每小时运行 `npm run ingest:news`。</p>
          </div>
          <JobRunner />
        </div>
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <Table>
            <thead>
              <tr>
                <Th>状态</Th>
                <Th>开始时间</Th>
                <Th>来源</Th>
                <Th>发现</Th>
                <Th>保存</Th>
                <Th>聚合</Th>
                <Th>错误</Th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <Td>
                    <Badge className={job.status === "failed" ? "bg-red-50 text-red-700" : ""}>{job.status}</Badge>
                  </Td>
                  <Td>{formatDateTime(job.startedAt)}</Td>
                  <Td>{job.sourcesChecked}</Td>
                  <Td>{job.articlesFound}</Td>
                  <Td>{job.articlesSaved}</Td>
                  <Td>{job.clustersTouched}</Td>
                  <Td className="max-w-sm truncate text-red-600">{job.error}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      </div>
    </main>
  );
}

