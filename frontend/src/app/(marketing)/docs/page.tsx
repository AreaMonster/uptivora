import type { Metadata } from "next";
import Link from "next/link";
import { DOCS } from "@/content/docs";

export const metadata: Metadata = { title: "Documentation" };

export default function DocsIndex() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-[32px] font-semibold tracking-[-0.02em]">Documentation</h1>
      <p className="mt-2 text-fg-muted">From your first check to running your own installation.</p>
      <ul className="mt-8 divide-y divide-line border-y border-line">
        {DOCS.map((d) => (
          <li key={d.slug}>
            <Link href={`/docs/${d.slug}`} className="group grid gap-1 py-4 sm:grid-cols-[220px_1fr] sm:gap-6">
              <span className="font-medium group-hover:underline">{d.title}</span>
              <span className="text-[15px] text-fg-muted">{d.summary}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
