import "dotenv/config";
import { PrismaClient, SourceType } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";

const adapter = new PrismaPg(process.env.DATABASE_URL ?? "postgresql://news:***@127.0.0.1:5432/news_aggregator");
const prisma = new PrismaClient({ adapter });

const categories = ["国内", "国际", "财经", "科技", "AI", "体育", "娱乐", "健康", "汽车"];

async function main() {
  const sources: Array<{
    id: string;
    name: string;
    type: SourceType;
    priority: number;
    query?: string | null;
    baseUrl?: string;
    categoryKeys: string[];
  }> = [
    {
      id: "Brave 新闻搜索",
      name: "Brave 新闻搜索",
      type: "brave_news",
      priority: 10,
      query: null,
      categoryKeys: categories,
    },
    {
      id: "Google 可编程搜索",
      name: "Google 可编程搜索",
      type: "google_cse",
      priority: 30,
      query: categories.join(" OR "),
      categoryKeys: categories,
    },
    {
      id: "OpenAI Web Search",
      name: "OpenAI Web Search",
      type: "openai_web_search",
      priority: 40,
      query: "今日热点新闻",
      categoryKeys: categories,
    },
    {
      id: "央视新闻 RSS",
      name: "中新网即时新闻 RSS",
      type: "crawler",
      priority: 20,
      baseUrl: "https://www.chinanews.com.cn/rss/scroll-news.xml",
      categoryKeys: ["国内", "国际"],
    },
  ];

  for (const source of sources) {
    const { id, ...data } = source;
    await prisma.dataSource.upsert({
      where: { id },
      update: data,
      create: { id, ...data },
    });
  }
}

main()
  .finally(async () => {
    await prisma.$disconnect();
  })
  .catch(async (error) => {
    console.error(error);
    await prisma.$disconnect();
    process.exit(1);
  });

