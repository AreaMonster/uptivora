"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, Suspense, useEffect, useState } from "react";
import {
  AlertOctagon,
  BookOpen,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  X,
} from "lucide-react";
import { Logo } from "@/components/logo";
import { Alert, Button, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

const NAV = [
  { href: "/dashboard", label: "Monitors", icon: LayoutDashboard, match: ["/dashboard", "/monitors"] },
  { href: "/incidents", label: "Incidents", icon: AlertOctagon, match: ["/incidents"] },
  { href: "/settings", label: "Settings", icon: Settings, match: ["/settings"] },
];

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
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  return <Frame>{children}</Frame>;
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <>
      {NAV.map(({ href, label, icon: Icon, match }) => {
        const active = match.some((m) => pathname === m || pathname.startsWith(`${m}/`));
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              active ? "bg-ink-700 text-fg" : "text-fg-muted hover:bg-ink-800 hover:text-fg",
            )}
          >
            <Icon className={cn("h-4 w-4", active && "text-accent")} aria-hidden />
            {label}
          </Link>
        );
      })}
    </>
  );
}

function StaticNavLinks() {
  return (
    <>
      {NAV.map(({ href, label, icon: Icon }) => (
        <Link key={href} href={href}
          className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-fg-muted">
          <Icon className="h-4 w-4" aria-hidden />
          {label}
        </Link>
      ))}
    </>
  );
}

function Frame({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  if (!me) return null;

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  const sidebar = (onNavigate?: () => void) => (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5">
        <Logo href="/dashboard" />
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4" aria-label="App">
        <Suspense fallback={<StaticNavLinks />}>
          <NavLinks onNavigate={onNavigate} />
        </Suspense>
        <Link
          href="/docs"
          className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-fg-muted hover:bg-ink-800 hover:text-fg"
        >
          <BookOpen className="h-4 w-4" aria-hidden /> Documentation
        </Link>
      </nav>
      <div className="border-t border-line p-4">
        <p className="truncate text-sm font-medium">{me.user.full_name || me.user.email}</p>
        <p className="truncate text-xs text-fg-subtle">{me.user.email}</p>
        <button
          type="button"
          onClick={signOut}
          className="mt-3 inline-flex items-center gap-2 text-xs text-fg-muted hover:text-fg"
        >
          <LogOut className="h-3.5 w-3.5" /> Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-ink-900 lg:block">
        {sidebar()}
      </aside>

      {/* Mobile top bar */}
      <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-ink-900/95 px-4 backdrop-blur lg:hidden">
        <Logo href="/dashboard" />
        <button type="button" onClick={() => setMobileOpen(true)} aria-label="Open menu"
          className="rounded-md p-2 text-fg-muted hover:text-fg">
          <Menu className="h-5 w-5" />
        </button>
      </div>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-line bg-ink-900">
            <button type="button" onClick={() => setMobileOpen(false)} aria-label="Close menu"
              className="absolute right-3 top-4 rounded-md p-2 text-fg-muted hover:text-fg">
              <X className="h-5 w-5" />
            </button>
            {sidebar(() => setMobileOpen(false))}
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Banners />
        {children}
      </main>
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
