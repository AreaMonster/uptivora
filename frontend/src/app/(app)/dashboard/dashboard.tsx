"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { Activity, CreditCard, Lock, Plus } from "lucide-react";
import {
  Alert,
  Badge,
  ButtonLink,
  EmptyState,
  PageHeader,
  Skeleton,
  StatusDot,
  StatusPill,
} from "@/components/ui";
import type { Monitor } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  cn,
  daysUntil,
  formatInterval,
  formatMs,
  formatUptime,
  hostOf,
  timeAgo,
} from "@/lib/format";
import { useApi } from "@/lib/use-api";

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" | "warn" }) {
  return (
    <div className="card px-5 py-4">
      <p className="text-xs font-medium text-fg-subtle">{label}</p>
      <p
        className={cn(
          "tnum mt-1.5 text-2xl font-semibold tracking-tight",
          tone === "up" && "text-up",
          tone === "down" && "text-down",
          tone === "warn" && "text-warn",
        )}
      >
        {value}
      </p>
    </div>
  );
}

export function Dashboard() {
  const { me } = useAuth();
  const params = useSearchParams();
  const { data: monitors, loading, error, reload } = useApi<Monitor[]>("/api/monitors", {
    refreshMs: 30_000,
  });

  const summary = useMemo(() => {
    const list = monitors ?? [];
    const uptimes = list.map((m) => m.uptime_24h).filter((u): u is number => u != null);
    return {
      up: list.filter((m) => m.status === "up").length,
      down: list.filter((m) => m.status === "down").length,
      paused: list.filter((m) => m.is_paused).length,
      avg: uptimes.length ? uptimes.reduce((a, b) => a + b, 0) / uptimes.length : null,
      ssl: list.filter((m) => {
        const d = daysUntil(m.ssl_expires_at);
        return d != null && d <= m.ssl_warning_days;
      }).length,
    };
  }, [monitors]);

  if (!me) return null;
  const { limits, usage } = me;
  const atLimit = limits.max_monitors != null && usage.active_monitors >= limits.max_monitors;
  const noPlan = limits.source === "no_plan";
  const limitLabel =
    limits.max_monitors == null
      ? `${usage.active_monitors} active monitors`
      : `${usage.active_monitors} of ${limits.max_monitors} active monitors`;

  return (
    <>
      <PageHeader
        title="Monitors"
        description={
          <span className="inline-flex flex-wrap items-center gap-2">
            {limitLabel}
            {limits.plan_name && <Badge tone="accent">{limits.plan_name} plan</Badge>}
            {limits.source === "licence" && <Badge tone="accent">{limits.edition} licence</Badge>}
            {limits.source === "admin" && <Badge>Administrator</Badge>}
          </span>
        }
        actions={
          !noPlan && (
            <ButtonLink
              href="/monitors/new"
              className={cn(atLimit && "pointer-events-none opacity-50")}
            >
              <Plus className="h-4 w-4" /> Add monitor
            </ButtonLink>
          )
        }
      />

      {params.get("welcome") && (
        <Alert tone="success" title="Welcome to Uptivora!" className="mb-6">
          We sent a confirmation link to {me.user.email}.
        </Alert>
      )}
      {atLimit && !noPlan && (
        <Alert tone="info" className="mb-6">
          You are using all {limits.max_monitors} active monitors of your plan. Pause or delete a
          monitor to add another.
        </Alert>
      )}
      {error && (
        <Alert tone="error" className="mb-6" action={
          <button className="text-xs underline" onClick={() => void reload()}>Retry</button>
        }>
          {error.message}
        </Alert>
      )}

      {noPlan ? (
        <EmptyState
          icon={<CreditCard className="h-5 w-5" />}
          title="Choose a plan to start monitoring"
          action={<ButtonLink href="/billing">Choose a plan</ButtonLink>}
        >
          Your account is ready, but it doesn’t have an active plan yet. Plans start at CHF 5 per
          month and can be cancelled any time.
        </EmptyState>
      ) : loading && !monitors ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : monitors && monitors.length === 0 ? (
        <EmptyState
          icon={<Activity className="h-5 w-5" />}
          title="Add your first monitor"
          action={<ButtonLink href="/monitors/new"><Plus className="h-4 w-4" /> Add monitor</ButtonLink>}
        >
          Paste the address of a website and Uptivora will start checking it within seconds.
        </EmptyState>
      ) : monitors ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Up" value={String(summary.up)} tone="up" />
            <Stat label="Down" value={String(summary.down)} tone={summary.down ? "down" : undefined} />
            <Stat label="Average uptime (24 h)" value={formatUptime(summary.avg)} />
            <Stat
              label="SSL certificates expiring"
              value={String(summary.ssl)}
              tone={summary.ssl ? "warn" : undefined}
            />
          </div>
          <MonitorList monitors={monitors} />
        </>
      ) : null}
    </>
  );
}

function MonitorList({ monitors }: { monitors: Monitor[] }) {
  const sorted = [...monitors].sort((a, b) => {
    const rank = (m: Monitor) => (m.status === "down" ? 0 : m.is_paused ? 2 : 1);
    return rank(a) - rank(b) || a.name.localeCompare(b.name);
  });
  return (
    <div className="card mt-6 overflow-hidden">
      <div className="hidden grid-cols-[minmax(0,2fr)_110px_110px_110px_130px] gap-4 border-b border-line px-5 py-3 text-xs font-medium text-fg-subtle xl:grid">
        <span>Monitor</span>
        <span>Status</span>
        <span className="text-right">Uptime 24 h</span>
        <span className="text-right">Response</span>
        <span className="text-right">Last check</span>
      </div>
      <ul className="divide-y divide-line">
        {sorted.map((m) => {
          const sslDays = daysUntil(m.ssl_expires_at);
          return (
            <li key={m.id}>
              <Link
                href={`/monitors/${m.id}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors hover:bg-ink-750/60 xl:grid-cols-[minmax(0,2fr)_110px_110px_110px_130px]"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <StatusDot status={m.status} className="shrink-0" />
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 truncate font-medium">
                      {m.name}
                      {sslDays != null && sslDays <= m.ssl_warning_days && (
                        <span title={`SSL certificate expires in ${sslDays} days`}>
                          <Lock className="h-3.5 w-3.5 text-warn" />
                        </span>
                      )}
                    </p>
                    <p className="truncate text-xs text-fg-subtle">
                      {hostOf(m.url)} · every {formatInterval(m.interval_seconds)}
                    </p>
                  </div>
                </div>
                <div className="xl:order-none">
                  <StatusPill status={m.status} />
                </div>
                <p className="tnum hidden text-right text-sm xl:block">{formatUptime(m.uptime_24h)}</p>
                <p className="tnum hidden text-right text-sm text-fg-muted xl:block">
                  {m.is_paused ? "—" : formatMs(m.last_response_ms)}
                </p>
                <p className="col-span-2 text-xs text-fg-subtle xl:col-span-1 xl:text-right xl:text-sm">
                  <span className="xl:hidden">
                    {formatUptime(m.uptime_24h)} uptime · {formatMs(m.last_response_ms)} ·{" "}
                  </span>
                  {m.is_paused ? "Paused" : timeAgo(m.last_checked_at)}
                </p>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
