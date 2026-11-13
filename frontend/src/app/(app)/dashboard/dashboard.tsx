"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { Plus } from "lucide-react";
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
          title="Choose a plan to start monitoring"
          action={<ButtonLink href="/billing">Choose a plan</ButtonLink>}
        >
          Your account is ready, but it doesn’t have an active plan yet. Plans start at CHF 5 per
          month and can be cancelled any time.
        </EmptyState>
      ) : loading && !monitors ? (
        <div className="space-y-3">
          <Skeleton className="h-8 w-80" />
          <Skeleton className="h-64" />
        </div>
      ) : monitors && monitors.length === 0 ? (
        <EmptyState
          title="Add your first monitor"
          action={<ButtonLink href="/monitors/new"><Plus className="h-4 w-4" /> Add monitor</ButtonLink>}
        >
          Paste the address of a website and Uptivora will start checking it within seconds.
        </EmptyState>
      ) : monitors ? (
        <>
          <Summary monitors={monitors} summary={summary} />
          <MonitorList monitors={monitors} />
        </>
      ) : null}
    </>
  );
}

function Summary({ monitors, summary }: {
  monitors: Monitor[];
  summary: { up: number; down: number; paused: number; avg: number | null; ssl: number };
}) {
  const active = monitors.length - summary.paused;
  const headline =
    summary.down > 0
      ? `${summary.down} of ${active} ${active === 1 ? "monitor" : "monitors"} ${summary.down === 1 ? "is" : "are"} down.`
      : active === 0
        ? "All monitors are paused."
        : `All ${active} ${active === 1 ? "monitor is" : "monitors are"} up.`;
  const notes = [
    summary.avg != null ? `${formatUptime(summary.avg)} uptime in the last 24 h` : null,
    summary.ssl ? `${summary.ssl} certificate${summary.ssl > 1 ? "s" : ""} expiring soon` : null,
    summary.paused ? `${summary.paused} paused` : null,
  ].filter(Boolean);
  return (
    <div className="mb-6">
      <p className={cn("flex items-center gap-2.5 text-lg font-semibold",
        summary.down ? "text-down-ink" : "text-fg")}>
        <StatusDot status={summary.down ? "down" : active ? "up" : "paused"} />
        {headline}
      </p>
      {notes.length > 0 && (
        <p className="mt-1 pl-[18px] text-sm text-fg-muted">
          {notes.map((n, i) => (
            <span key={n}>
              {i > 0 && " · "}
              <span className={cn(n?.includes("certificate") && "text-warn-ink")}>{n}</span>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function MonitorList({ monitors }: { monitors: Monitor[] }) {
  const sorted = [...monitors].sort((a, b) => {
    const rank = (m: Monitor) => (m.status === "down" ? 0 : m.is_paused ? 2 : 1);
    return rank(a) - rank(b) || a.name.localeCompare(b.name);
  });
  return (
    <div className="card overflow-hidden">
      <table className="w-full table-fixed text-sm">
        <thead className="border-b border-line">
          <tr className="text-left">
            <th className="eyebrow px-4 py-2.5 font-medium">Monitor</th>
            <th className="eyebrow hidden w-28 px-3 py-2.5 font-medium sm:table-cell">Status</th>
            <th className="eyebrow hidden w-24 px-3 py-2.5 text-right font-medium md:table-cell">24 h</th>
            <th className="eyebrow hidden w-28 px-3 py-2.5 text-right font-medium md:table-cell">Response</th>
            <th className="eyebrow w-36 px-4 py-2.5 text-right font-medium">Checked</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {sorted.map((m) => {
            const sslDays = daysUntil(m.ssl_expires_at);
            const sslWarn = sslDays != null && sslDays <= m.ssl_warning_days;
            return (
              <tr key={m.id} className={cn("group relative hover:bg-hover", m.status === "down" && "bg-down-soft")}>
                <td className="max-w-0 px-4 py-3">
                  <Link href={`/monitors/${m.id}`} className="flex items-center gap-3 after:absolute after:inset-0">
                    <StatusDot status={m.status} className="sm:hidden" />
                    <span className="min-w-0">
                      <span className="block truncate font-medium group-hover:underline">{m.name}</span>
                      <span className="block truncate font-mono text-xs text-fg-subtle">
                        {hostOf(m.url)} · {formatInterval(m.interval_seconds)}
                        {sslWarn && <span className="text-warn-ink"> · cert {sslDays} d</span>}
                      </span>
                    </span>
                  </Link>
                </td>
                <td className="hidden px-3 py-3 sm:table-cell"><StatusPill status={m.status} /></td>
                <td className="tnum hidden px-3 py-3 text-right font-mono md:table-cell">{formatUptime(m.uptime_24h)}</td>
                <td className="tnum hidden px-3 py-3 text-right font-mono text-fg-muted md:table-cell">
                  {m.is_paused ? "—" : formatMs(m.last_response_ms)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-right text-fg-muted">
                  {m.is_paused ? "paused" : timeAgo(m.last_checked_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
