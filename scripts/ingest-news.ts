import "dotenv/config";
import { ingestNews } from "@/lib/news/ingest";
import { prisma } from "@/lib/db";

ingestNews()
  .then((summary) => {
    console.log(JSON.stringify(summary, null, 2));
    process.exitCode = 0;
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
    process.exit(process.exitCode ?? 0);
  });

