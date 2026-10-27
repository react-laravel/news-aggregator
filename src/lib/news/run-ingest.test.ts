import { EventEmitter } from "node:events";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const { spawn } = vi.hoisted(() => ({ spawn: vi.fn() }));
vi.mock("node:child_process", () => ({ spawn }));
import { runIngest } from "./run-ingest";

describe("production ingestion process lifecycle", () => {
  let child: EventEmitter & { stdout: EventEmitter & { setEncoding: ReturnType<typeof vi.fn> } };
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
    child = Object.assign(new EventEmitter(), { stdout: Object.assign(new EventEmitter(), { setEncoding: vi.fn() }) });
    spawn.mockReturnValue(child);
  });
  afterEach(() => { vi.unstubAllEnvs(); vi.clearAllMocks(); });
  it("uses fixed arguments and waits for process close after summary", async () => {
    let settled = false;
    const pending = runIngest("source_1").then((value) => { settled = true; return value; });
    const summary = { jobId: "job", sourcesChecked: 1, articlesFound: 2, articlesSaved: 2, clustersTouched: 1 };
    child.stdout.emit("data", JSON.stringify(summary));
    await Promise.resolve(); expect(settled).toBe(false);
    child.emit("close", 0); expect(await pending).toEqual(summary);
    expect(spawn).toHaveBeenCalledWith("/usr/local/libexec/dogeow-test-news-collect", ["web", "source_1"], {
      stdio: ["ignore", "pipe", "ignore"], env: { PATH: "/usr/bin:/bin", NODE_ENV: "production" },
    });
  });
  it("preserves lock-busy or maintenance errors without invoking shell", async () => {
    const pending = runIngest();
    child.stdout.emit("data", JSON.stringify({ error: "采集任务正在运行或发布维护中，请稍后再试" }));
    child.emit("close", 75);
    await expect(pending).rejects.toThrow("发布维护中");
  });
  it("rejects invalid source identifiers before starting any child", async () => {
    await expect(runIngest("x;id")).rejects.toThrow("数据源不存在"); expect(spawn).not.toHaveBeenCalled();
  });
  it("rejects oversized output without killing an in-flight task", async () => {
    const pending = runIngest(); child.stdout.emit("data", "x".repeat(17000));
    child.emit("close", 0); await expect(pending).rejects.toThrow("采集结果过大");
  });
});
