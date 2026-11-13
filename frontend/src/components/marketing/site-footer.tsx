import Link from "next/link";
import { Logo } from "@/components/logo";

const LINKS = [
  { href: "/pricing", label: "Pricing" },
  { href: "/self-hosted", label: "Self-hosted licence" },
  { href: "/docs", label: "Documentation" },
  { href: "/docs/self-hosting", label: "Installation guide" },
  { href: "/login", label: "Sign in" },
  { href: "/register", label: "Create account" },
];

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="container-page flex flex-col gap-8 py-10 md:flex-row md:justify-between">
        <div className="max-w-sm">
          <Logo />
          <p className="mt-3 text-sm text-fg-muted">
            Uptime and certificate monitoring by email. This website sets no cookies until you
            sign in and runs no analytics.
          </p>
        </div>
        <ul className="grid grid-cols-2 gap-x-10 gap-y-2 text-sm sm:grid-cols-3">
          {LINKS.map((l) => (
            <li key={l.href}>
              <Link href={l.href} className="text-fg-muted hover:text-fg">
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
      <div className="container-page flex flex-col gap-1 border-t border-line py-4 font-mono text-[11px] text-fg-subtle sm:flex-row sm:justify-between">
        <span>© Uptivora</span>
        <span>Prices in Swiss francs (CHF)</span>
      </div>
    </footer>
  );
}
