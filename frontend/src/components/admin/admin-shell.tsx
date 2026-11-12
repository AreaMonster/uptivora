"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, Suspense, useEffect, useState } from "react";
import {
  ArrowLeft,
  FlaskConical,
  Gauge,
  Layers,
  Menu,
  Radar,
  Receipt,
  ScrollText,
  Server,
  ShieldAlert,
  Users,
  X,
} from "lucide-react";
import { LogoMark } from "@/components/logo";
import { ButtonLink, Spinner } from "@/components/ui";
import { api, type PublicConfig } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

type NavItem = { href: string; label: string; icon: typeof Gauge; hostedOnly?: boolean; devOnly?: boolean };

const NAV: NavItem[] = [
  { href: "/admin", label: "Overview", icon: Gauge },
  { href: "/admin/users", label: "Users", icon: Users },
  { href: "/admin/monitors", label: "Monitors", icon: Radar },
  { href: "/admin/plans", label: "Plans & pricing", icon: Layers, hostedOnly: true },
  { href: "/admin/billing", label: "Billing & licences", icon: Receipt, hostedOnly: true },
  { href: "/admin/system", label: "System", icon: Server },
  { href: "/admin/logs", label: "Logs", icon: ScrollText },
  { href: "/admin/dev", label: "Dev tools", icon: FlaskConical, devOnly: true },
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
    return <div className="grid min-h-screen place-items-center"><Spinner className="h-6 w-6" /></div>;
  }
  if (me.user.role !== "admin") {
    return (
      <div className="grid min-h-screen place-items-center px-4">
        <div className="card max-w-md p-8 text-center">
          <ShieldAlert className="mx-auto h-8 w-8 text-warn" />
          <h1 className="mt-4 text-lg font-semibold">Administrator access required</h1>
          <p className="mt-2 text-sm text-fg-muted">Your account cannot open the admin area.</p>
          <ButtonLink href="/dashboard" variant="secondary" className="mt-6">Back to your dashboard</ButtonLink>
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
    && (!n.devOnly || (config && config.environment !== "production")));
  return (
    <>
      {items.map(({ href, label, icon: Icon }) => {
        const active = href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
        return (
          <Link key={href} href={href} onClick={onNavigate} aria-current={active ? "page" : undefined}
            className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              active ? "bg-ink-700 text-fg" : "text-fg-muted hover:bg-ink-800 hover:text-fg")}>
            <Icon className={cn("h-4 w-4", active && "text-warn")} aria-hidden />
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

  const sidebar = (onNavigate?: () => void) => (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <LogoMark />
        <span className="text-[15px] font-semibold tracking-[0.18em]">UPTIVORA</span>
        <span className="rounded bg-warn/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-warn ring-1 ring-warn/30">
          Admin
        </span>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Admin">
        <Suspense fallback={null}>
          <AdminNav config={config} onNavigate={onNavigate} />
        </Suspense>
      </nav>
      <div className="space-y-3 border-t border-line p-4">
        {config && (
          <p className="text-xs text-fg-subtle">
            {config.edition === "hosted" ? "Hosted" : "Self-hosted"} · {config.environment} · v{config.version}
          </p>
        )}
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-xs text-fg-muted hover:text-fg">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to app
        </Link>
        <p className="truncate text-xs text-fg-subtle">{me?.user.email}</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen border-t-2 border-warn/70 lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-line bg-ink-900 lg:block">{sidebar()}</aside>
      <div className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-ink-900/95 px-4 backdrop-blur lg:hidden">
        <span className="flex items-center gap-2"><LogoMark /><span className="text-xs font-bold uppercase tracking-wider text-warn">Admin</span></span>
        <button type="button" onClick={() => setOpen(true)} aria-label="Open menu" className="rounded-md p-2 text-fg-muted">
          <Menu className="h-5 w-5" />
        </button>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-line bg-ink-900">
            <button type="button" onClick={() => setOpen(false)} aria-label="Close menu"
              className="absolute right-3 top-4 rounded-md p-2 text-fg-muted"><X className="h-5 w-5" /></button>
            {sidebar(() => setOpen(false))}
          </div>
        </div>
      )}
      <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
    </div>
  );
}
