import "dotenv/config";
import { defineConfig } from "prisma/config";

const databaseUrl = process.env.DATABASE_URL ?? "postgresql://news:news@127.0.0.1:5432/news_aggregator?schema=public";

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
    seed: "tsx -r tsconfig-paths/register prisma/seed.ts",
  },
  datasource: {
    url: databaseUrl,
  },
});
