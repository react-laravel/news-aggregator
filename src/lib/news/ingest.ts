import { Prisma, type Article, type DataSource } from "@prisma/client";
import { prisma } from "@/lib/db";
import { adapters } from "./adapters";
import { clusterFingerprint, normalizeUrl, titleSimilarity } from "./normalize";
import { chooseCanonical, qualityScore } from "./ranking";
import { translateIfNeeded } from "./translate";
import type { CandidateArticle } from "./types";

export type IngestSummary = {
  jobId: string;
  sourcesChecked: number;
  articlesFound: number;
  articlesSaved: number;
  clustersTouched: number;
};

async function ingestSources(jobId: string, sources: DataSource[]): Promise<Omit<IngestSummary, "jobId">> {
  let sourcesChecked = 0;
  let articlesFound = 0;
  let articlesSaved = 0;
  const touchedClusters = new Set<string>();

  for (const source of sources) {
    sourcesChecked += 1;
    try {
      const adapter = adapters[source.type];
      const candidates = await adapter.fetch(source);
      articlesFound += candidates.length;
      for (const candidate of candidates) {
        try {
          const article: Article = await saveCandidate(source.id, candidate);
          articlesSaved += 1;
          if (article.clusterId) touchedClusters.add(article.clusterId);
        } catch (error) {
          console.error(`保存新闻失败 ${candidate.url}`, error);
        }
      }
      await prisma.dataSource.update({
        where: { id: source.id },
        data: { lastFetchedAt: new Date(), lastStatus: "success", lastError: null },
      });
    } catch (error) {
      await prisma.dataSource.update({
        where: { id: source.id },
        data: {
          lastFetchedAt: new Date(),
          lastStatus: "failed",
          lastError: error instanceof Error ? error.message : String(error),
        },
      });
    }
  }

  await prisma.ingestJob.update({
    where: { id: jobId },
    data: {
      status: "success",
      finishedAt: new Date(),
      sourcesChecked,
      articlesFound,
      articlesSaved,
      clustersTouched: touchedClusters.size,
    },
  });

  return { sourcesChecked, articlesFound, articlesSaved, clustersTouched: touchedClusters.size };
}

async function findCluster(category: string, title: string) {
  const recent = await prisma.newsCluster.findMany({
    where: {
      category,
      updatedAt: {
        gte: new Date(Date.now() - 36 * 60 * 60 * 1000),
      },
    },
    take: 25,
    orderBy: { updatedAt: "desc" },
  });

  const matched = recent.find((cluster) => titleSimilarity(cluster.title, title) >= 0.58);
  if (matched) return matched;

  return prisma.newsCluster.create({
    data: {
      category,
      title,
      fingerprint: `${clusterFingerprint(title, category)}:${Date.now().toString(36)}`,
    },
  });
}

async function refreshCanonical(clusterId: string) {
  const articles = await prisma.article.findMany({
    where: { clusterId },
    include: { source: true },
  });
  const canonical = chooseCanonical(articles);
  if (!canonical) return;
  await prisma.newsCluster.update({
    where: { id: clusterId },
    data: {
      canonicalArticleId: canonical.id,
      title: canonical.titleZh,
      category: canonical.category,
    },
  });
}

async function saveCandidate(sourceId: string, candidate: CandidateArticle) {
  const normalizedUrl = normalizeUrl(candidate.url);
  const translated = await translateIfNeeded(candidate.titleOriginal, candidate.summaryOriginal);
  const category = candidate.category || "国内";
  const cluster = await findCluster(category, translated.titleZh || candidate.titleOriginal);
  const score = qualityScore({
    summaryOriginal: candidate.summaryOriginal,
    summaryZh: translated.summaryZh,
    imageUrl: candidate.imageUrl,
    publishedAt: candidate.publishedAt,
  });

  const article = await prisma.article.upsert({
    where: {
      sourceId_normalizedUrl: {
        sourceId,
        normalizedUrl,
      },
    },
    update: {
      clusterId: cluster.id,
      titleOriginal: candidate.titleOriginal,
      titleZh: translated.titleZh,
      summaryOriginal: candidate.summaryOriginal,
      summaryZh: translated.summaryZh,
      language: translated.language,
      category,
      imageUrl: candidate.imageUrl,
      publishedAt: candidate.publishedAt,
      qualityScore: score,
      raw: candidate.raw === undefined ? Prisma.JsonNull : (candidate.raw as Prisma.InputJsonValue),
    },
    create: {
      sourceId,
      clusterId: cluster.id,
      url: candidate.url,
      normalizedUrl,
      sourceName: candidate.sourceName,
      titleOriginal: candidate.titleOriginal,
      titleZh: translated.titleZh,
      summaryOriginal: candidate.summaryOriginal,
      summaryZh: translated.summaryZh,
      language: translated.language,
      category,
      imageUrl: candidate.imageUrl,
      publishedAt: candidate.publishedAt,
      qualityScore: score,
      raw: candidate.raw === undefined ? Prisma.JsonNull : (candidate.raw as Prisma.InputJsonValue),
    },
  });

  await refreshCanonical(cluster.id);
  return article;
}

export async function ingestNews(): Promise<IngestSummary> {
  const existingRunning = await prisma.ingestJob.findFirst({
    where: {
      status: "running",
      startedAt: { gte: new Date(Date.now() - 20 * 60 * 1000) },
    },
  });
  if (existingRunning) {
    throw new Error(`采集任务正在运行：${existingRunning.id}`);
  }

  const job = await prisma.ingestJob.create({ data: { status: "running" } });

  try {
    const sources = await prisma.dataSource.findMany({
      where: { enabled: true },
      orderBy: { priority: "asc" },
    });
    const summary = await ingestSources(job.id, sources);
    return { jobId: job.id, ...summary };
  } catch (error) {
    await prisma.ingestJob.update({
      where: { id: job.id },
      data: {
        status: "failed",
        finishedAt: new Date(),
        error: error instanceof Error ? error.message : String(error),
      },
    });
    throw error;
  }
}

export async function ingestSingleSource(sourceId: string): Promise<IngestSummary> {
  const existingRunning = await prisma.ingestJob.findFirst({
    where: {
      status: "running",
      startedAt: { gte: new Date(Date.now() - 20 * 60 * 1000) },
    },
  });
  if (existingRunning) {
    throw new Error(`采集任务正在运行：${existingRunning.id}`);
  }

  const source = await prisma.dataSource.findUnique({ where: { id: sourceId } });
  if (!source) {
    throw new Error("数据源不存在");
  }

  const job = await prisma.ingestJob.create({ data: { status: "running" } });
  try {
    const summary = await ingestSources(job.id, [source]);
    return { jobId: job.id, ...summary };
  } catch (error) {
    await prisma.ingestJob.update({
      where: { id: job.id },
      data: {
        status: "failed",
        finishedAt: new Date(),
        error: error instanceof Error ? error.message : String(error),
      },
    });
    throw error;
  }
}
