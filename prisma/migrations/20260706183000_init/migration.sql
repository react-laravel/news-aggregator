CREATE TYPE "SourceType" AS ENUM ('crawler', 'brave_news', 'google_cse', 'openai_web_search');
CREATE TYPE "JobStatus" AS ENUM ('running', 'success', 'failed');

CREATE TABLE "DataSource" (
  "id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "type" "SourceType" NOT NULL,
  "enabled" BOOLEAN NOT NULL DEFAULT true,
  "priority" INTEGER NOT NULL DEFAULT 100,
  "baseUrl" TEXT,
  "query" TEXT,
  "categoryKeys" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  "lastFetchedAt" TIMESTAMP(3),
  "lastStatus" TEXT,
  "lastError" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "DataSource_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "NewsCluster" (
  "id" TEXT NOT NULL,
  "fingerprint" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "category" TEXT NOT NULL,
  "canonicalArticleId" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "NewsCluster_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "Article" (
  "id" TEXT NOT NULL,
  "sourceId" TEXT NOT NULL,
  "clusterId" TEXT,
  "url" TEXT NOT NULL,
  "normalizedUrl" TEXT NOT NULL,
  "sourceName" TEXT NOT NULL,
  "titleOriginal" TEXT NOT NULL,
  "titleZh" TEXT NOT NULL,
  "summaryOriginal" TEXT,
  "summaryZh" TEXT,
  "language" TEXT NOT NULL DEFAULT 'zh',
  "category" TEXT NOT NULL,
  "imageUrl" TEXT,
  "publishedAt" TIMESTAMP(3),
  "qualityScore" INTEGER NOT NULL DEFAULT 0,
  "raw" JSONB,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Article_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "IngestJob" (
  "id" TEXT NOT NULL,
  "status" "JobStatus" NOT NULL DEFAULT 'running',
  "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "finishedAt" TIMESTAMP(3),
  "sourcesChecked" INTEGER NOT NULL DEFAULT 0,
  "articlesFound" INTEGER NOT NULL DEFAULT 0,
  "articlesSaved" INTEGER NOT NULL DEFAULT 0,
  "clustersTouched" INTEGER NOT NULL DEFAULT 0,
  "error" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "IngestJob_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "NewsCluster_fingerprint_key" ON "NewsCluster"("fingerprint");
CREATE UNIQUE INDEX "NewsCluster_canonicalArticleId_key" ON "NewsCluster"("canonicalArticleId");
CREATE UNIQUE INDEX "Article_sourceId_normalizedUrl_key" ON "Article"("sourceId", "normalizedUrl");

CREATE INDEX "DataSource_enabled_priority_idx" ON "DataSource"("enabled", "priority");
CREATE INDEX "NewsCluster_category_updatedAt_idx" ON "NewsCluster"("category", "updatedAt");
CREATE INDEX "Article_category_publishedAt_idx" ON "Article"("category", "publishedAt");
CREATE INDEX "Article_normalizedUrl_idx" ON "Article"("normalizedUrl");
CREATE INDEX "Article_clusterId_idx" ON "Article"("clusterId");
CREATE INDEX "Article_createdAt_idx" ON "Article"("createdAt");
CREATE INDEX "IngestJob_startedAt_idx" ON "IngestJob"("startedAt");
CREATE INDEX "IngestJob_status_idx" ON "IngestJob"("status");

ALTER TABLE "Article"
  ADD CONSTRAINT "Article_sourceId_fkey" FOREIGN KEY ("sourceId") REFERENCES "DataSource"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "Article"
  ADD CONSTRAINT "Article_clusterId_fkey" FOREIGN KEY ("clusterId") REFERENCES "NewsCluster"("id") ON DELETE SET NULL ON UPDATE CASCADE;

ALTER TABLE "NewsCluster"
  ADD CONSTRAINT "NewsCluster_canonicalArticleId_fkey" FOREIGN KEY ("canonicalArticleId") REFERENCES "Article"("id") ON DELETE SET NULL ON UPDATE CASCADE;

