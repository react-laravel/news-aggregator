import { spawn } from "node:child_process";
import type { IngestSummary } from "./ingest";

// Production ingestion owns an OS lock for its complete process lifetime.
// An HTTP disconnect never cancels the child or releases that lock early.
export async function runIngest(sourceId?: string): Promise<IngestSummary> {
  if (process.env.NODE_ENV !== "production") {
    const { ingestNews, ingestSingleSource } = await import("./ingest");
    return sourceId ? ingestSingleSource(sourceId) : ingestNews();
  }
  if (sourceId !== undefined && !/^[A-Za-z0-9_-]{1,128}$/.test(sourceId)) {
    throw new Error("数据源不存在");
  }
  return new Promise((resolve, reject) => {
    const child = spawn("/usr/local/libexec/dogeow-test-news-collect", ["web", ...(sourceId ? [sourceId] : [])], {
      stdio: ["ignore", "pipe", "ignore"],
      env: { PATH: "/usr/bin:/bin", NODE_ENV: "production" },
    });
    let output = "";
    let overflow = false;
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      if (Buffer.byteLength(output) + Buffer.byteLength(chunk) > 16384) overflow = true;
      else output += chunk;
    });
    child.on("error", () => reject(new Error("无法启动采集任务")));
    child.on("close", (code) => {
      try {
        if (overflow) throw new Error("采集结果过大");
        const result = JSON.parse(output);
        if (code !== 0) throw new Error(typeof result.error === "string" ? result.error : "采集失败");
        if (!result || typeof result.jobId !== "string" ||
            !["sourcesChecked", "articlesFound", "articlesSaved", "clustersTouched"].every((key) => Number.isInteger(result[key]) && result[key] >= 0)) {
          throw new Error("采集结果无效");
        }
        resolve(result as IngestSummary);
      } catch (error) {
        reject(error instanceof SyntaxError ? new Error("采集任务未返回有效结果") : error);
      }
    });
  });
}
