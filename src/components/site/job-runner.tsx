"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";

export function JobRunner() {
  const [message, setMessage] = useState("");
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    setMessage("");
    const response = await fetch("/api/admin/jobs/run", { method: "POST" });
    const data = await response.json().catch(() => ({}));
    setRunning(false);
    setMessage(response.ok ? `已完成：保存 ${data.articlesSaved ?? 0} 条新闻` : data.error || "运行失败");
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Button onClick={run} disabled={running}>
        <Play size={16} />
        {running ? "采集中" : "手动采集"}
      </Button>
      {message ? <span className="text-sm text-zinc-500 dark:text-zinc-400">{message}</span> : null}
    </div>
  );
}
