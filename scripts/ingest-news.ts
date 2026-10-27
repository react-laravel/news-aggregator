import "dotenv/config";
import { ingestNews, ingestSingleSource } from "@/lib/news/ingest";
import { prisma } from "@/lib/db";

const args = process.argv.slice(2);
if (args.length > 1 || (args.length === 1 && !/^[A-Za-z0-9_-]{1,128}$/.test(args[0]))) {
  throw new Error("Invalid source id");
}

(args.length ? ingestSingleSource(args[0]) : ingestNews())
  .then((summary) => {
    console.log(JSON.stringify(summary, null, 2));
    process.exitCode = 0;
  })
  .catch((error) => {
    console.log(JSON.stringify({ error: error instanceof Error ? error.message : "采集失败" }));
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
    process.exit(process.exitCode ?? 0);
  });

