import { BottomNav } from "@/components/site/bottom-nav";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatsChart } from "@/components/site/stats-chart";
import { prisma } from "@/lib/db";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

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

function partsInShanghai(date: Date) {
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return {
    year: get("year"),
    month: get("month"),
    day: get("day"),
    hour: get("hour"),
  };
}

function hourKey(date: Date) {
  const parts = partsInShanghai(date);
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}`;
}

function dayKey(date: Date) {
  const parts = partsInShanghai(date);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function formatHour(date: Date) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(date);
}

function formatDay(date: Date) {
  const parts = partsInShanghai(date);
  const weekday = new Intl.DateTimeFormat("zh-CN", {
    weekday: "short",
    timeZone: "Asia/Shanghai",
  }).format(date);
  return `${Number(parts.month)}/${Number(parts.day)} ${weekday}`;
}

function countBy<T extends string>(items: Date[], keyFn: (date: Date) => T) {
  const counts = new Map<T, number>();
  for (const item of items) {
    const key = keyFn(item);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

function getShanghaiDayStartUtc(date: Date) {
  const parts = partsInShanghai(date);
  return new Date(`${parts.year}-${parts.month}-${parts.day}T00:00:00+08:00`);
}

export default async function StatsPage() {
  const now = new Date();
  const hourlyBuckets = Array.from({ length: 24 }, (_, index) => {
    const date = startOfHour(now);
    date.setHours(date.getHours() - (23 - index));
    return date;
  });
  const todayStart = getShanghaiDayStartUtc(now);
  const dailyBuckets = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(todayStart);
    date.setDate(date.getDate() - (6 - index));
    return date;
  });
  const sevenDayStart = dailyBuckets[0] ?? startOfDay(now);

  const [recentArticles, latestArticle, total] = await Promise.all([
    prisma.article.findMany({
      where: { createdAt: { gte: sevenDayStart } },
      select: { createdAt: true },
    }),
    prisma.article.findFirst({
      orderBy: { createdAt: "desc" },
      select: { createdAt: true },
    }),
    prisma.article.count(),
  ]);

  const createdTimes = recentArticles.map((article) => article.createdAt);
  const hourlyCounts = countBy(createdTimes.filter((date) => date >= hourlyBuckets[0]!), hourKey);
  const dailyCounts = countBy(createdTimes, dayKey);
  const hourlyData = hourlyBuckets.map((bucket) => ({
    label: formatHour(bucket),
    value: hourlyCounts.get(hourKey(bucket)) ?? 0,
  }));
  const dailyData = dailyBuckets.map((bucket) => ({
    label: formatDay(bucket).replace(" ", "\n"),
    value: dailyCounts.get(dayKey(bucket)) ?? 0,
  }));

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
          <CardContent>
            <StatsChart title="每小时更新量" data={hourlyData} xAxisInterval={3} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>最近 7 天</CardTitle>
          </CardHeader>
          <CardContent>
            <StatsChart title="每天更新量" data={dailyData} xAxisInterval={0} className="h-64" />
          </CardContent>
        </Card>
      </div>
      <BottomNav />
    </main>
  );
}
