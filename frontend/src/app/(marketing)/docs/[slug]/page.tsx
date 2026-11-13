import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DOCS, getDoc } from "@/content/docs";

export function generateStaticParams() {
  return DOCS.map((d) => ({ slug: d.slug }));
}

export async function generateMetadata({ params }: PageProps<"/docs/[slug]">): Promise<Metadata> {
  const doc = getDoc((await params).slug);
  return { title: doc ? doc.title : "Documentation", description: doc?.summary };
}

export default async function DocPage({ params }: PageProps<"/docs/[slug]">) {
  const doc = getDoc((await params).slug);
  if (!doc) notFound();
  return (
    <article className="max-w-3xl">
      <h1 className="text-[32px] font-semibold tracking-[-0.02em]">{doc.title}</h1>
      <p className="mt-2 text-fg-muted">{doc.summary}</p>
      <div className="prose-uv mt-8">{doc.body}</div>
    </article>
  );
}
