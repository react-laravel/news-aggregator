"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { DataSource, SourceType } from "@prisma/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Td } from "@/components/ui/table";
import { NEWS_CATEGORIES } from "@/lib/constants";

export function SourceRow({ source }: { source: DataSource }) {
  const [enabled, setEnabled] = useState(source.enabled);
  const [priority, setPriority] = useState(String(source.priority));
  const [saving, setSaving] = useState(false);

  async function save(nextEnabled = enabled) {
    setSaving(true);
    await fetch(`/api/admin/sources/${source.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: nextEnabled, priority: Number(priority) }),
    });
    setSaving(false);
  }

  return (
    <tr>
      <Td>
        <div className="font-medium text-zinc-950 dark:text-zinc-50">{source.name}</div>
        <div className="text-xs text-zinc-500 dark:text-zinc-400">{source.baseUrl || source.query || "未设置查询"}</div>
      </Td>
      <Td>{source.type}</Td>
      <Td>
        <Input className="w-20" value={priority} onChange={(event) => setPriority(event.target.value)} inputMode="numeric" />
      </Td>
      <Td>{source.categoryKeys.join("、") || "全部"}</Td>
      <Td>
        <Switch
          checked={enabled}
          onCheckedChange={(checked) => {
            setEnabled(checked);
            void save(checked);
          }}
        />
      </Td>
      <Td>{source.lastStatus || "未运行"}</Td>
      <Td>
        <Button variant="outline" size="sm" onClick={() => save()} disabled={saving}>
          {saving ? "保存中" : "保存"}
        </Button>
      </Td>
    </tr>
  );
}

export function SourceCreateForm() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
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
      setMessage("创建失败，请检查字段和后台 token");
      return;
    }
    event.currentTarget.reset();
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-lg border border-zinc-200 bg-white p-4 md:grid-cols-6 dark:border-zinc-800 dark:bg-zinc-900">
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
      <div className="md:col-span-6 flex items-center gap-3">
        <Button type="submit" disabled={saving}>
          {saving ? "创建中" : "新增数据源"}
        </Button>
        {message ? <span className="text-sm text-red-600 dark:text-red-400">{message}</span> : null}
      </div>
    </form>
  );
}
