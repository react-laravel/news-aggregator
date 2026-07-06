"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { DataSource, SourceType } from "@prisma/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { NEWS_CATEGORIES } from "@/lib/constants";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";

export function SourceCard({ source }: { source: DataSource }) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);
  const [enabled, setEnabled] = useState(source.enabled);
  const [priority, setPriority] = useState(String(source.priority));
  const [saving, setSaving] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [message, setMessage] = useState("");

  async function save(nextEnabled = enabled) {
    setSaving(true);
    await fetch(`/api/admin/sources/${source.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: nextEnabled, priority: Number(priority) }),
    });
    setSaving(false);
  }

  async function ingest() {
    setIngesting(true);
    setMessage("");
    const response = await fetch(`/api/admin/sources/${source.id}/ingest`, { method: "POST" });
    const data = (await response.json().catch(() => ({}))) as { articlesFound?: number; articlesSaved?: number; error?: string };
    setIngesting(false);
    if (!response.ok) {
      setMessage(data.error || "采集失败");
      return;
    }
    setMessage(`发现 ${data.articlesFound ?? 0} 条，保存 ${data.articlesSaved ?? 0} 条`);
    router.refresh();
  }

  return (
    <section className="min-w-0 space-y-3 rounded-lg bg-white p-4 shadow-sm dark:border dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-none">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <h2 className="min-w-0 flex-1 truncate text-base font-semibold text-zinc-950 dark:text-zinc-50">{source.name}</h2>
        <span className="shrink-0 rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">{source.type}</span>
      </div>

      <div className="grid grid-cols-[1fr_auto_auto] items-center gap-2">
        <div className="min-w-0 text-sm">
          <div className="truncate text-zinc-700 dark:text-zinc-200">{source.lastFetchedAt ? `${formatRelativeTime(source.lastFetchedAt)}采集` : "未采集"}</div>
          <div className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">{source.lastStatus || "未运行"}</div>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => setExpanded((current) => !current)}>
          {expanded ? "收起" : "修改"}
        </Button>
        <Button size="sm" className="w-full" onClick={ingest} disabled={saving || ingesting}>
          {ingesting ? "采集中" : "测试采集"}
        </Button>
      </div>

      {message ? <p className="break-words rounded-md bg-zinc-100 p-2 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">{message}</p> : null}

      {expanded ? (
        <div className="space-y-4 pt-4 dark:border-t dark:border-zinc-800">
          <p className="break-all text-xs text-zinc-500 dark:text-zinc-400">{source.baseUrl || source.query || "未设置查询"}</p>
          <dl className="grid min-w-0 grid-cols-2 gap-3 text-sm">
            <div className="min-w-0">
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">优先级</dt>
              <dd className="mt-1">
                <Input className="h-9 w-full" value={priority} onChange={(event) => setPriority(event.target.value)} inputMode="numeric" />
              </dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">启用</dt>
              <dd className="mt-2">
                <Switch
                  checked={enabled}
                  onCheckedChange={(checked) => {
                    setEnabled(checked);
                    void save(checked);
                  }}
                />
              </dd>
            </div>
            <div className="col-span-2 min-w-0">
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">分类</dt>
              <dd className="mt-1 break-words text-zinc-800 dark:text-zinc-200">{source.categoryKeys.join("、") || "全部"}</dd>
            </div>
            <div className="col-span-2 min-w-0">
              <dt className="text-xs text-zinc-500 dark:text-zinc-400">最近采集</dt>
              <dd className="mt-1 text-zinc-800 dark:text-zinc-200">{source.lastFetchedAt ? formatDateTime(source.lastFetchedAt) : "无"}</dd>
            </div>
          </dl>
          {source.lastError ? <p className="break-words rounded-md bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">{source.lastError}</p> : null}
          <Button variant="outline" size="sm" className="w-full" onClick={() => save()} disabled={saving || ingesting}>
            {saving ? "保存中" : "保存设置"}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

export function SourceCreateForm() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setSaving(true);
    setMessage("");
    const form = new FormData(formElement);
    const categoryKeys = String(form.get("categoryKeys") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const response = await fetch("/api/admin/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: String(form.get("name") || ""),
        type: String(form.get("type") || "crawler") as SourceType,
        priority: Number(form.get("priority") || 100),
        baseUrl: String(form.get("baseUrl") || ""),
        query: String(form.get("query") || ""),
        categoryKeys,
      }),
    });
    setSaving(false);
    if (!response.ok) {
      const data = (await response.json().catch(() => ({}))) as { error?: string };
      setMessage(data.error || "创建失败，请检查字段和后台 token");
      return;
    }
    formElement.reset();
    setOpen(false);
    router.refresh();
  }

  return (
    <section className="min-w-0 space-y-3">
      <Button type="button" className="w-full sm:w-auto" onClick={() => setOpen((current) => !current)}>
        {open ? "收起添加" : "添加数据源"}
      </Button>

      {open ? (
        <form onSubmit={submit} className="grid min-w-0 gap-3 rounded-lg bg-white p-4 shadow-sm md:grid-cols-2 dark:border dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-none">
          <Input name="name" placeholder="名称" required />
          <Select name="type" defaultValue="crawler">
            <option value="crawler">crawler</option>
            <option value="brave_news">brave_news</option>
            <option value="google_cse">google_cse</option>
            <option value="openai_web_search">openai_web_search</option>
          </Select>
          <Input name="priority" placeholder="优先级" defaultValue="100" inputMode="numeric" />
          <Input name="baseUrl" placeholder="RSS URL，可空" />
          <Input name="query" placeholder="搜索词，可空" />
          <Input name="categoryKeys" placeholder={`分类逗号分隔，如 ${NEWS_CATEGORIES.slice(0, 3).join(",")}`} />
          <div className="flex flex-col gap-2 md:col-span-2 sm:flex-row sm:items-center">
            <Button type="submit" disabled={saving}>
              {saving ? "创建中" : "新增数据源"}
            </Button>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              取消
            </Button>
            {message ? <span className="text-sm text-red-600 dark:text-red-400">{message}</span> : null}
          </div>
        </form>
      ) : null}
    </section>
  );
}
