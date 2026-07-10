# Linux 裸机部署

## 1. 环境变量

复制 `.env.example` 为 `.env`，至少配置：

- `DATABASE_URL`
- `ADMIN_TOKEN`
- `BRAVE_SEARCH_API_KEY`
- `OPENAI_API_KEY`

Google 搜索是可选项，需要同时配置 `GOOGLE_API_KEY` 和 `GOOGLE_CSE_ID`。

## 2. 初始化

```bash
npm ci
npm run prisma:generate
npm run prisma:migrate
npm run prisma:seed
npm run build
```

## 3. 启动应用

```bash
npm run start
```

默认监听 `3000`。建议用 Nginx 反向代理到本服务。

## 4. 每小时采集

把 `deploy/news-ingest.service` 和 `deploy/news-ingest.timer` 复制到 `/etc/systemd/system/`，按实际路径修改 `WorkingDirectory` 和 `EnvironmentFile`。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now news-ingest.timer
```

