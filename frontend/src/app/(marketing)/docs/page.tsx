import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { DOCS } from "@/content/docs";

export const metadata: Metadata = { title: "Documentation" };

export default function DocsIndex() {
  return (
    <div>
      <h1 className="text-3xl font-semibold tracking-tight">Documentation</h1>
      <p className="mt-2 max-w-2xl text-fg-muted">
        Everything about monitoring with Uptivora, from your first check to running your own
        installation.
      </p>
      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        {DOCS.map((d) => (
          <Link key={d.slug} href={`/docs/${d.slug}`} className="card group p-5 transition-colors hover:border-line-strong">
            <p className="flex items-center justify-between font-medium">
              {d.title}
              <ArrowRight className="h-4 w-4 text-fg-subtle transition-transform group-hover:translate-x-0.5" />
            </p>
            <p className="mt-1 text-sm text-fg-muted">{d.summary}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
