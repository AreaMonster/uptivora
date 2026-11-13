import Link from "next/link";
import { DOCS } from "@/content/docs";

export default function DocsLayout({ children }: LayoutProps<"/docs">) {
  return (
    <div className="container-page grid grid-cols-[minmax(0,1fr)] gap-10 py-12 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
      <aside>
        <p className="eyebrow">Documentation</p>
        <nav className="mt-3 flex gap-4 overflow-x-auto pb-2 lg:flex-col lg:gap-0 lg:pb-0" aria-label="Docs">
          <Link href="/docs" className="shrink-0 py-1.5 text-sm text-fg-muted hover:text-fg">
            Overview
          </Link>
          {DOCS.map((d) => (
            <Link key={d.slug} href={`/docs/${d.slug}`} className="shrink-0 py-1.5 text-sm text-fg-muted hover:text-fg">
              {d.title}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
