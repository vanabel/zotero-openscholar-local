import Link from "next/link";

const links = [
  { href: "/", label: "概览" },
  { href: "/library", label: "文献库" },
  { href: "/chat", label: "问答" },
  { href: "/review", label: "综述" },
  { href: "/settings", label: "设置" },
];

export function Nav() {
  return (
    <header className="border-b border-mist-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="block font-semibold leading-tight text-ink-950">
          <span className="block">Zotero × OpenScholar 本地库</span>
          <span className="mt-0.5 block text-xs font-normal text-ink-500">
            流程对齐 OpenScholar 式证据与引用；LLM 与语料均为自管
          </span>
        </Link>
        <nav className="flex flex-wrap items-center gap-3 text-sm text-ink-700">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-2 py-1 hover:bg-accent-soft hover:text-accent"
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
