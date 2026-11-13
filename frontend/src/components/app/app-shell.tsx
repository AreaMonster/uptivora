"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, Suspense, useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { Alert, Button, Spinner } from "@/components/ui";
import { api, type PublicConfig } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

const NAV = [
  { href: "/dashboard", label: "Monitors", match: ["/dashboard", "/monitors"] },
  { href: "/incidents", label: "Incidents", match: ["/incidents"] },
  { href: "/billing", label: "Billing", match: ["/billing"], hostedOnly: true },
  { href: "/settings", label: "Settings", match: ["/settings"] },
];

/** Billing exists only where limits come from a per-user plan (hosted edition). */
function useNav() {
  const { me } = useAuth();
  const hosted = me?.limits.scope === "user";
  return NAV.filter((n) => !("hostedOnly" in n) || hosted);
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Gate>{children}</Gate>
    </AuthProvider>
  );
}

function Gate({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !me) {
      const next = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [loading, me, router]);

  if (!me) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }
  return <Frame>{children}</Frame>;
}

function NavLinks({ vertical, onNavigate }: { vertical?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const nav = useNav();
  return (
    <>
      {nav.map(({ href, label, match }) => {
        const active = match.some((m) => pathname === m || pathname.startsWith(`${m}/`));
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "text-sm transition-colors",
              vertical
                ? cn("border-b border-line py-3 text-[15px]", active ? "font-semibold" : "text-fg-muted")
                : cn(
                    "flex h-14 items-center border-b-2",
                    active ? "border-fg font-medium text-fg" : "border-transparent text-fg-muted hover:text-fg",
                  ),
            )}
          >
            {label}
          </Link>
        );
      })}
    </>
  );
}

function StaticNavLinks() {
  const nav = useNav();
  return (
    <>
      {nav.map(({ href, label }) => (
        <Link key={href} href={href} className="flex h-14 items-center border-b-2 border-transparent text-sm text-fg-muted">
          {label}
        </Link>
      ))}
    </>
  );
}

function Frame({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [testMode, setTestMode] = useState(false);
  useEffect(() => {
    api<PublicConfig>("/api/public/config").then((c) => setTestMode(c.billing_test_mode), () => {});
  }, []);
  if (!me) return null;

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  const isAdmin = me.user.role === "admin";

  return (
    <div className="flex min-h-screen flex-col">
      {testMode && me.limits.scope === "user" && (
        <div className="bg-warn px-4 py-1 text-center font-mono text-[11px] font-medium uppercase tracking-wider text-canvas">
          Test mode — payments are simulated, no money is charged
        </div>
      )}
      <header className="border-b border-line bg-canvas">
        <div className="container-page flex h-14 items-center gap-8">
          <Logo href="/dashboard" />
          <nav className="hidden items-stretch gap-6 md:flex" aria-label="App">
            <Suspense fallback={<StaticNavLinks />}>
              <NavLinks />
            </Suspense>
          </nav>
          <div className="ml-auto hidden items-center gap-5 text-sm md:flex">
            {isAdmin && <Link href="/admin" className="text-fg-muted hover:text-fg">Admin</Link>}
            <Link href="/docs" className="text-fg-muted hover:text-fg">Docs</Link>
            <span className="h-4 w-px bg-line-strong" aria-hidden />
            <span className="max-w-[200px] truncate text-fg-muted" title={me.user.email}>
              {me.user.full_name || me.user.email}
            </span>
            <button type="button" onClick={signOut} className="text-fg-muted hover:text-fg">
              Sign out
            </button>
          </div>
          <button
            type="button"
            className="ml-auto -mr-2 px-2 py-1 font-mono text-xs uppercase tracking-wide text-fg-muted md:hidden"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? "Close" : "Menu"}
          </button>
        </div>
        {menuOpen && (
          <nav className="container-page flex flex-col border-t border-line pb-3 md:hidden" aria-label="App menu">
            <Suspense fallback={null}>
              <NavLinks vertical onNavigate={() => setMenuOpen(false)} />
            </Suspense>
            {isAdmin && <Link href="/admin" className="border-b border-line py-3 text-[15px] text-fg-muted">Admin</Link>}
            <Link href="/docs" className="border-b border-line py-3 text-[15px] text-fg-muted">Docs</Link>
            <p className="pt-3 text-sm text-fg-subtle">{me.user.email}</p>
            <button type="button" onClick={signOut} className="mt-2 self-start text-sm underline">
              Sign out
            </button>
          </nav>
        )}
      </header>

      <main className="container-page flex-1 py-8">
        <Banners />
        {children}
      </main>

      {me.limits.scope === "instance" && (
        <footer className="border-t border-line">
          <div className="container-page py-3 font-mono text-[11px] text-fg-subtle">
            {me.limits.source === "licence" && me.limits.licensee
              ? `Self-hosted · ${me.limits.edition} licence · licensed to ${me.limits.licensee}`
              : "Self-hosted · evaluation mode, no licence installed"}
          </div>
        </footer>
      )}
    </div>
  );
}

function Banners() {
  const { me } = useAuth();
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!me) return null;

  async function resend() {
    setBusy(true);
    try {
      await api("/api/auth/resend-verification", { method: "POST" });
      setSent(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-6 space-y-3 empty:hidden">
      {!me.user.email_verified && (
        <Alert
          tone="warning"
          title="Please confirm your email address"
          action={
            sent ? (
              <span className="text-xs">Sent — check your inbox</span>
            ) : (
              <Button size="sm" variant="secondary" onClick={resend} loading={busy}>
                Resend email
              </Button>
            )
          }
        >
          Alerts are only sent to confirmed addresses.
        </Alert>
      )}
      {me.limits.source === "unlicensed" && (
        <Alert tone="info" title="Evaluation mode">
          No licence is installed: up to {me.limits.max_monitors} monitors and checks every{" "}
          {Math.round(me.limits.min_interval_seconds / 60)} minutes.
        </Alert>
      )}
    </div>
  );
}
