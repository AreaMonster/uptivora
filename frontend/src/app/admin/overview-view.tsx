"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, Badge, PageHeader, Skeleton } from "@/components/ui";
import { SetupChecklist } from "@/components/admin/invitations";
import { TOOLTIP_STYLE } from "@/components/app/charts";
import type { AdminHealth, AdminOverview, SystemEventRow } from "@/lib/admin-types";
import { cn, formatDuration, formatMoney, formatNumber, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type RecentIncident = {
  id: string;
  monitor_name: string;
  owner_email: string;
  started_at: string;
  resolved_at: string | null;
  duration_seconds: number;
  cause: string;
};

export function Kpi({ label, value, sub, tone }: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "warn";
}) {
  return (
    <div className="border-t border-fg pt-2.5">
      <p className="text-xs text-fg-subtle">{label}</p>
      <p className={cn("tnum mt-1 font-mono text-2xl font-medium tracking-tight",
        tone === "up" && "text-up-ink", tone === "down" && "text-down-ink", tone === "warn" && "text-warn-ink")}>
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-fg-subtle">{sub}</p>}
    </div>
  );
}

export function AdminOverviewView() {
  const { data: ov, error } = useApi<AdminOverview>("/api/admin/overview", { refreshMs: 30_000 });
  const { data: health } = useApi<AdminHealth>("/api/admin/health", { refreshMs: 30_000 });
  const { data: incidents } = useApi<RecentIncident[]>("/api/admin/incidents/recent?limit=8", { refreshMs: 60_000 });
  const { data: warnings } = useApi<SystemEventRow[]>("/api/admin/logs?level=warning&limit=6", { refreshMs: 60_000 });

  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!ov) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-24" />)}
      </div>
    );
  }

  const subs = ov.subscriptions;
  return (
    <>
      <PageHeader title="Overview" description={`${ov.edition === "hosted" ? "Hosted" : "Self-hosted"} edition · ${ov.environment}`} />
      {ov.edition === "selfhosted" && <SetupChecklist />}

      {health && (
        <Link href="/admin/system" className="mb-6 block">
          {health.status === "ok" ? (
            <p className="flex items-center gap-2.5 text-sm text-fg-muted hover:text-fg">
              <span className="h-2 w-2 rounded-full bg-up" aria-hidden />
              Running normally — {health.workers.filter((w) => w.alive).length} worker(s), database {health.database.latency_ms} ms.
            </p>
          ) : (
            <div className="border-l-[3px] border-warn bg-warn-soft px-4 py-3 text-sm">
              <p className="font-semibold">Needs attention</p>
              <ul className="mt-1 list-disc pl-5 text-fg-muted">{health.issues.map((i) => <li key={i}>{i}</li>)}</ul>
            </div>
          )}
        </Link>
      )}

      <div className="grid grid-cols-2 gap-x-6 gap-y-6 lg:grid-cols-4">
        <Kpi label="Users" value={formatNumber(ov.users.total)} sub={`+${ov.users.new_7d} in 7 days · ${ov.users.active_30d} active`} />
        {subs ? (
          <>
            <Kpi label="Active subscriptions" value={formatNumber(subs.active)}
              sub={`${subs.past_due} past due · ${subs.cancelled} cancelling`} tone="up" />
            <Kpi label="Monthly recurring revenue" value={formatMoney(subs.mrr.real_cents, subs.mrr.currency)}
              sub={subs.mrr.test_cents ? `+ ${formatMoney(subs.mrr.test_cents, subs.mrr.currency)} TEST MODE` : "real payments only"} />
          </>
        ) : (
          <>
            <Kpi label="Licence" value={ov.licence?.installed ? (ov.licence.edition ?? "") : "Evaluation"}
              sub={ov.licence?.licensee ?? ov.licence?.error ?? "No licence installed"} />
            <Kpi label="Monitor limit" value={ov.licence?.limits ? (ov.licence.limits.max_monitors || "∞").toString() : "3"} />
          </>
        )}
        <Kpi label="Monitors" value={formatNumber(ov.monitors.active)}
          sub={`${ov.monitors.paused} paused · ${ov.monitors.admin_paused} by admin`} />
        <Kpi label="Down right now" value={formatNumber(ov.monitors.down)} tone={ov.monitors.down ? "down" : undefined}
          sub={`${ov.incidents.open} open incidents`} />
        <Kpi label="Checks per minute" value={String(ov.checks.per_minute)}
          sub={`${formatNumber(ov.checks.last_24h)} in 24 h`} />
        <Kpi label="Failed checks (1 h)" value={formatNumber(ov.checks.failed_last_hour)}
          tone={ov.checks.failed_last_hour ? "warn" : undefined} sub={`of ${formatNumber(ov.checks.last_hour)}`} />
        <Kpi label="Alert emails" value={formatNumber(ov.emails.sent_24h)} sub={`sent in 24 h · ${ov.emails.queued} queued · ${ov.emails.failed_7d} failed (7 d)`}
          tone={ov.emails.failed_7d ? "warn" : undefined} />
      </div>

      {ov.billing_test_mode && (
        <Alert tone="warning" className="mt-4">Billing runs in TEST MODE: subscriptions and payments are simulated.</Alert>
      )}

      <section className="card mt-6 p-5 sm:p-6">
        <h2 className="font-semibold">Checks in the last 24 hours</h2>
        {ov.checks_by_hour.length === 0 ? (
          <p className="mt-4 text-sm text-fg-subtle">No checks recorded yet — is the worker running?</p>
        ) : (
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ov.checks_by_hour.map((p) => ({ ...p, ok: p.total - p.failed }))}
                margin={{ top: 4, right: 4, bottom: 0, left: -12 }}>
                <CartesianGrid stroke="var(--color-line)" vertical={false} />
                <XAxis dataKey="t" stroke="var(--color-fg-subtle)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} axisLine={false}
                  tickFormatter={(v) => new Date(v).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })} minTickGap={28} />
                <YAxis stroke="var(--color-fg-subtle)" fontSize={11} fontFamily="var(--font-mono)" tickLine={false} axisLine={false} width={48} />
                <Tooltip cursor={{ fill: "var(--color-hover)" }}
                  contentStyle={TOOLTIP_STYLE}
                  labelFormatter={(v) => new Date(String(v)).toLocaleString("en-GB")} />
                <Bar dataKey="ok" name="Successful" stackId="c" fill="var(--color-up)" isAnimationActive={false} />
                <Bar dataKey="failed" name="Failed" stackId="c" fill="var(--color-down)" isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="card overflow-hidden">
          <h2 className="border-b border-line px-5 py-4 font-semibold">Recent incidents (all customers)</h2>
          {incidents?.length === 0 && <p className="px-5 py-6 text-sm text-fg-subtle">No incidents yet.</p>}
          <ul className="divide-y divide-line">
            {incidents?.map((i) => (
              <li key={i.id} className="px-5 py-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate font-medium">{i.monitor_name}</span>
                  {i.resolved_at ? <Badge tone="up">Resolved</Badge> : <Badge tone="down">Ongoing</Badge>}
                </div>
                <p className="mt-0.5 truncate text-xs text-fg-subtle">
                  {i.owner_email} · {timeAgo(i.started_at)} · {formatDuration(i.duration_seconds)} · {i.cause}
                </p>
              </li>
            ))}
          </ul>
        </section>
        <section className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-5 py-4">
            <h2 className="font-semibold">Recent warnings & errors</h2>
            <Link href="/admin/logs" className="text-xs text-fg-muted hover:text-fg">All logs</Link>
          </div>
          {warnings?.length === 0 && <p className="px-5 py-6 text-sm text-fg-subtle">Nothing to report.</p>}
          <ul className="divide-y divide-line">
            {warnings?.map((w) => (
              <li key={w.id} className="px-5 py-3 text-sm">
                <div className="flex items-center gap-2">
                  <Badge tone={w.level === "warning" ? "warn" : "down"}>{w.level}</Badge>
                  <span className="text-xs text-fg-subtle">{w.source} · {timeAgo(w.created_at)}</span>
                </div>
                <p className="mt-1 break-words text-fg-muted">{w.message}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
