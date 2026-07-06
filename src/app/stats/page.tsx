import { BottomNav } from "@/components/site/bottom-nav";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { prisma } from "@/lib/db";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

type CountRow = {
  bucket: Date;
  count: bigint;
};

function toCountMap(rows: CountRow[]) {
  return new Map(rows.map((row) => [new Date(row.bucket).toISOString(), Number(row.count)]));
}

function startOfHour(date: Date) {
  const next = new Date(date);
  next.setMinutes(0, 0, 0);
  return next;
}

function startOfDay(date: Date) {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

function formatHour(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(date);
}

function formatDay(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    weekday: "short",
    timeZone: "Asia/Shanghai",
  }).format(date);
}

export default async function StatsPage() {
  const now = new Date();
  const hourlyBuckets = Array.from({ length: 24 }, (_, index) => {
    const date = startOfHour(now);
    date.setHours(date.getHours() - (23 - index));
    return date;
  });
  const dailyBuckets = Array.from({ length: 7 }, (_, index) => {
    const date = startOfDay(now);
    date.setDate(date.getDate() - (6 - index));
    return date;
  });

  const [hourRows, dayRows, latestArticle, total] = await Promise.all([
    prisma.$queryRaw<CountRow[]>`
      SELECT date_trunc('hour', "createdAt") AS bucket, COUNT(*)::bigint AS count
      FROM "Article"
      WHERE "createdAt" >= NOW() - INTERVAL '24 hours'
      GROUP BY bucket
      ORDER BY bucket ASC
    `,
    prisma.$queryRaw<CountRow[]>`
      SELECT date_trunc('day', "createdAt") AS bucket, COUNT(*)::bigint AS count
      FROM "Article"
      WHERE "createdAt" >= NOW() - INTERVAL '7 days'
      GROUP BY bucket
      ORDER BY bucket ASC
    `,
    prisma.article.findFirst({
      orderBy: { createdAt: "desc" },
      select: { createdAt: true },
    }),
    prisma.article.count(),
  ]);

  const hourlyCounts = toCountMap(hourRows);
  const dailyCounts = toCountMap(dayRows);
  const maxHour = Math.max(1, ...hourlyBuckets.map((bucket) => hourlyCounts.get(bucket.toISOString()) ?? 0));
  const maxDay = Math.max(1, ...dailyBuckets.map((bucket) => dailyCounts.get(bucket.toISOString()) ?? 0));

  return (
    <main className="min-h-screen bg-zinc-50 pb-24 dark:bg-zinc-950">
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-5">
        <header className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-2xl font-semibold tracking-normal text-zinc-950 dark:text-zinc-50">更新统计</h1>
            <Badge>共 {total} 条</Badge>
          </div>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            最后更新：{formatRelativeTime(latestArticle?.createdAt)}
            {latestArticle?.createdAt ? ` · ${formatDateTime(latestArticle.createdAt)}` : ""}
          </p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>最近 24 小时</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {hourlyBuckets.map((bucket) => {
              const count = hourlyCounts.get(bucket.toISOString()) ?? 0;
              return (
                <div key={bucket.toISOString()} className="grid grid-cols-[52px_1fr_42px] items-center gap-3 text-sm">
                  <span className="text-zinc-500 dark:text-zinc-400">{formatHour(bucket)}</span>
                  <div className="h-2 rounded-full bg-zinc-100 dark:bg-zinc-800">
                    <div className="h-2 rounded-full bg-zinc-950 dark:bg-zinc-50" style={{ width: `${Math.max(3, (count / maxHour) * 100)}%` }} />
                  </div>
                  <span className="text-right font-medium text-zinc-950 dark:text-zinc-50">{count}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>最近 7 天</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {dailyBuckets.map((bucket) => {
              const count = dailyCounts.get(bucket.toISOString()) ?? 0;
              return (
                <div key={bucket.toISOString()} className="grid grid-cols-[86px_1fr_42px] items-center gap-3 text-sm">
                  <span className="text-zinc-500 dark:text-zinc-400">{formatDay(bucket)}</span>
                  <div className="h-2 rounded-full bg-zinc-100 dark:bg-zinc-800">
                    <div className="h-2 rounded-full bg-zinc-950 dark:bg-zinc-50" style={{ width: `${Math.max(3, (count / maxDay) * 100)}%` }} />
                  </div>
                  <span className="text-right font-medium text-zinc-950 dark:text-zinc-50">{count}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>
      <BottomNav />
    </main>
  );
}
