/**
 * 可选：使用 PM2 常驻/守护进程（生产或长期本机调试）。
 * 先执行 `npm run setup` 装好 API 虚拟环境与前端依赖。
 *
 *   npx pm2 start ecosystem.config.cjs
 *   npx pm2 logs
 *   npx pm2 stop all
 *
 * 注意：API 使用 uvicorn --reload 时由 PM2 拉起也可热重载；
 * 若只想开发热重载，更推荐根目录 `pnpm dev` / `npm run dev`。
 */
module.exports = {
  apps: [
    {
      name: "zotero-api",
      cwd: "./apps/api",
      script: "./.venv/bin/python",
      args: "-m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
      interpreter: "none",
      watch: false,
    },
    {
      name: "zotero-web",
      cwd: "./apps/web",
      script: "npm",
      args: "run dev",
      interpreter: "none",
      env: { FORCE_COLOR: "1" },
    },
  ],
};
