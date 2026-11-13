import Link from "next/link";
import type { ReactNode } from "react";
import { LEGAL_STATUS, OPERATOR } from "@/content/legal/operator";

export const LEGAL_PAGES = [
  { href: "/legal", label: "Legal notice" },
  { href: "/privacy", label: "Privacy policy" },
  { href: "/terms", label: "Terms of service" },
  { href: "/licence-agreement", label: "Self-hosted licence agreement" },
  { href: "/dpa", label: "Data processing agreement" },
];

/** Renders an operator value; unfilled placeholders are highlighted while in draft. */
export function Op({ v }: { v: keyof typeof OPERATOR }) {
  const value = OPERATOR[v];
  if (value.startsWith("[")) {
    return <mark className="rounded-[2px] bg-warn-soft px-1 text-warn-ink">{value}</mark>;
  }
  return <>{value}</>;
}

/** Notes for the reviewing lawyer; disappear once the texts are marked as reviewed. */
export function ReviewNote({ children }: { children: ReactNode }) {
  if (LEGAL_STATUS.reviewed) return null;
  return (
    <aside className="my-4 border-l-[3px] border-accent bg-accent-soft px-4 py-2.5 text-sm not-italic">
      <strong className="font-semibold text-fg">For review: </strong>
      <span className="text-fg-muted">{children}</span>
    </aside>
  );
}

export function LegalPage({ title, intro, children }: { title: string; intro?: ReactNode; children: ReactNode }) {
  return (
    <div className="container-page grid grid-cols-[minmax(0,1fr)] gap-10 py-12 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
      <aside>
        <p className="eyebrow">Legal</p>
        <nav className="mt-3 flex gap-4 overflow-x-auto pb-2 lg:flex-col lg:gap-0 lg:pb-0" aria-label="Legal">
          {LEGAL_PAGES.map((p) => (
            <Link key={p.href} href={p.href} className="shrink-0 py-1.5 text-sm text-fg-muted hover:text-fg">
              {p.label}
            </Link>
          ))}
        </nav>
      </aside>
      <article className="max-w-3xl">
        {!LEGAL_STATUS.reviewed && (
          <p className="mb-8 border-l-[3px] border-warn bg-warn-soft px-4 py-3 text-sm">
            <strong className="font-semibold">Draft.</strong>{" "}
            <span className="text-fg-muted">
              This text has not been reviewed by a lawyer yet and details in highlighted brackets
              are still missing. It does not apply until this notice is gone.
            </span>
          </p>
        )}
        <h1 className="text-[32px] font-semibold tracking-[-0.02em]">{title}</h1>
        <p className="mt-2 font-mono text-xs text-fg-subtle">Version of {LEGAL_STATUS.version}</p>
        {intro && <div className="mt-4 text-[15px] text-fg-muted">{intro}</div>}
        <div className="prose-uv mt-8">{children}</div>
      </article>
    </div>
  );
}
