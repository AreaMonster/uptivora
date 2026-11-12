import Link from "next/link";
import { DOCS } from "@/content/docs";

export default function DocsLayout({ children }: LayoutProps<"/docs">) {
  return (
    <div className="container-page grid gap-10 py-12 lg:grid-cols-[220px_1fr]">
      <aside>
        <p className="text-xs font-semibold uppercase tracking-wider text-fg-subtle">Documentation</p>
        <nav className="mt-3 flex gap-1 overflow-x-auto pb-2 lg:flex-col lg:pb-0" aria-label="Docs">
          <Link href="/docs" className="shrink-0 rounded-md px-2.5 py-1.5 text-sm text-fg-muted hover:bg-ink-800 hover:text-fg">
            Overview
          </Link>
          {DOCS.map((d) => (
            <Link
              key={d.slug}
              href={`/docs/${d.slug}`}
              className="shrink-0 rounded-md px-2.5 py-1.5 text-sm text-fg-muted hover:bg-ink-800 hover:text-fg"
            >
              {d.title}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
