import type { Metadata } from "next";
import "./globals.css";
import { GlobalTaskQueueBanner } from "@/components/GlobalTaskQueueBanner";
import { ActiveTasksProvider } from "@/components/ActiveTasksProvider";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Zotero 本地文献 RAG（OpenScholar 风格）",
  description:
    "扫描 Zotero PDF，建立索引；问答与综述采用 OpenScholar 式带引用证据链（自管 LLM，非官方 OpenScholar 服务）。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <ActiveTasksProvider>
          <Nav />
          <GlobalTaskQueueBanner />
          <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
        </ActiveTasksProvider>
      </body>
    </html>
  );
}
