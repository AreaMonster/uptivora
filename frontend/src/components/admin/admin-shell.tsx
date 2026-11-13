"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, Suspense, useEffect, useState } from "react";
import { LogoMark } from "@/components/logo";
import { ButtonLink, Spinner } from "@/components/ui";
import { api, type PublicConfig } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

type NavItem = {
  href: string;
  label: string;
  hostedOnly?: boolean;
  selfHostedOnly?: boolean;
  devOnly?: boolean;
};

const NAV: NavItem[] = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/users", label: "Users" },
  { href: "/admin/monitors", label: "Monitors" },
  { href: "/admin/plans", label: "Plans & pricing", hostedOnly: true },
  { href: "/admin/billing", label: "Billing & licences", hostedOnly: true },
  { href: "/admin/licence", label: "Licence", selfHostedOnly: true },
  { href: "/admin/system", label: "System" },
  { href: "/admin/logs", label: "Logs" },
  { href: "/admin/dev", label: "Dev tools", devOnly: true },
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <AdminGate>{children}</AdminGate>
    </AuthProvider>
  );
}

function AdminGate({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !me) {
      router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  }, [loading, me, router]);

  if (!me) {
    return <div className="grid min-h-screen place-items-center"><Spinner className="h-5 w-5" /></div>;
  }
  if (me.user.role !== "admin") {
    return (
      <div className="container-page pt-24">
        <div className="max-w-md">
          <h1 className="text-[28px] font-semibold tracking-[-0.02em]">Administrators only</h1>
          <p className="mt-2 text-fg-muted">Your account cannot open the admin area.</p>
          <ButtonLink href="/dashboard" variant="secondary" className="mt-6">Back to your monitors</ButtonLink>
        </div>
      </div>
    );
  }
  return <AdminFrame>{children}</AdminFrame>;
}

function useConfig(): PublicConfig | null {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  useEffect(() => {
    api<PublicConfig>("/api/public/config").then(setConfig, () => setConfig(null));
  }, []);
  return config;
}

function AdminNav({ config, onNavigate }: { config: PublicConfig | null; onNavigate?: () => void }) {
  const pathname = usePathname();
  const items = NAV.filter((n) => (!n.hostedOnly || config?.edition === "hosted")
    && (!n.selfHostedOnly || config?.edition === "selfhosted")
    && (!n.devOnly || (config && config.environment !== "production")));
  return (
    <>
      {items.map(({ href, label }) => {
        const active = href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
        return (
          <Link key={href} href={href} onClick={onNavigate} aria-current={active ? "page" : undefined}
            className={cn("-ml-px block border-l-2 py-1.5 pl-3 text-sm transition-colors",
              active ? "border-fg font-medium text-fg" : "border-transparent text-fg-muted hover:text-fg")}>
            {label}
          </Link>
        );
      })}
    </>
  );
}

function AdminFrame({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const config = useConfig();
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="bg-primary text-on-primary">
        <div className="mx-auto flex h-12 w-full max-w-[1280px] items-center gap-3 px-4 sm:px-6">
          <LogoMark />
          <span className="font-semibold tracking-[-0.02em]">uptivora</span>
          <span className="font-mono text-xs uppercase tracking-wider opacity-60">admin</span>
          {config && (
            <span className="hidden font-mono text-[11px] opacity-60 sm:inline">
              · {config.edition === "hosted" ? "hosted" : "self-hosted"} · {config.environment} · v{config.version}
            </span>
          )}
          <div className="ml-auto flex items-center gap-5 text-sm">
            <span className="hidden max-w-[220px] truncate opacity-70 md:inline">{me?.user.email}</span>
            <Link href="/dashboard" className="opacity-80 hover:opacity-100">Back to app</Link>
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
              className="font-mono text-xs uppercase tracking-wide opacity-80 lg:hidden">
              {open ? "Close" : "Menu"}
            </button>
          </div>
        </div>
      </header>
      {open && (
        <nav className="border-b border-line px-4 py-3 lg:hidden" aria-label="Admin menu">
          <Suspense fallback={null}>
            <AdminNav config={config} onNavigate={() => setOpen(false)} />
          </Suspense>
        </nav>
      )}
      <div className="mx-auto flex w-full max-w-[1280px] flex-1 gap-10 px-4 sm:px-6">
        <aside className="hidden w-44 shrink-0 pt-8 lg:block">
          <nav className="sticky top-8 border-l border-line" aria-label="Admin">
            <Suspense fallback={null}>
              <AdminNav config={config} />
            </Suspense>
          </nav>
        </aside>
        <main className="min-w-0 flex-1 py-8">{children}</main>
      </div>
    </div>
  );
}
