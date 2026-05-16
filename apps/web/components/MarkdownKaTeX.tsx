"use client";

import "katex/dist/katex.min.css";

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { normalizeMathDelimiters } from "@/lib/normalizeMathDelimiters";

const mdComponents: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  h1: ({ children }) => <h1 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-3 text-sm font-semibold first:mt-0">{children}</h3>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink-950">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-2 border-mist-300 pl-3 text-ink-700">{children}</blockquote>
  ),
  code: ({ className, children, ...props }) => {
    const inline = !className;
    if (inline) {
      return (
        <code className="rounded bg-mist-100 px-1 py-0.5 font-mono text-[0.9em] text-ink-900" {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className={`block w-full font-mono text-[0.85em] ${className ?? ""}`} {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg border border-mist-200 bg-mist-50 p-3 text-[0.85em] last:mb-0 [&>code]:bg-transparent">
      {children}
    </pre>
  ),
  a: ({ href, children }) => (
    <a href={href} className="text-accent underline underline-offset-2 hover:opacity-90" rel="noreferrer noopener" target="_blank">
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-mist-200" />,
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto">
      <table className="w-full border-collapse text-left text-[0.95em]">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-mist-200 bg-mist-50 px-2 py-1 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-mist-200 px-2 py-1">{children}</td>,
};

type Props = {
  /** Markdown；公式支持 `$…$`、`$$…$$`、`\(...\)`、`\[...\]`（后两者会规范为 $ / $$） */
  content: string;
  className?: string;
};

/**
 * Markdown + KaTeX（含 `\(...\)` / `\[...\]` 定界符）。
 */
const rehypeKatexOpts = { throwOnError: false, strict: false, output: "htmlAndMathml" as const };

export default function MarkdownKaTeX({ content, className }: Props) {
  const source = normalizeMathDelimiters(content);
  return (
    <div className={`prose-math max-w-none ${className ?? ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
        rehypePlugins={[[rehypeKatex, rehypeKatexOpts]]}
        components={mdComponents}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
