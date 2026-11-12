"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Alert, Badge, PageHeader, Skeleton, Toggle } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { AdminHealth } from "@/lib/admin-types";
import { formatBytes, formatDuration, formatNumber, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-fg-muted">{label}</dt>
      <dd className="tnum min-w-0 break-words text-right">{value}</dd>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-5">
      <h2 className="mb-2 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

export function SystemView() {
  const { data: h, error, reload } = useApi<AdminHealth>("/api/admin/health", { refreshMs: 15_000 });
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!h) return <Skeleton className="h-96" />;
  const disk = h.server.disk;
  const diskPct = disk ? Math.round((disk.used_bytes / disk.total_bytes) * 100) : null;

  return (
    <>
      <PageHeader title="System" description={`Updated ${timeAgo(h.app.now)}`}
        actions={<button className="text-sm text-fg-muted hover:text-fg" onClick={() => void reload()}>Refresh</button>} />

      {h.status === "ok" ? (
        <Alert tone="success" title="All systems operational" className="mb-6" />
      ) : (
        <Alert tone="warning" title="Attention needed" className="mb-6">
          <ul className="list-disc pl-5">{h.issues.map((i) => <li key={i}>{i}</li>)}</ul>
        </Alert>
      )}

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        <Card title="Application">
          <dl className="divide-y divide-line">
            <Row label="Version" value={h.app.version} />
            <Row label="Edition" value={h.app.edition} />
            <Row label="Environment" value={h.app.environment} />
            <Row label="API uptime" value={formatDuration(h.app.api_uptime_seconds)} />
            <Row label="Host" value={h.app.hostname} />
            <Row label="Python" value={h.app.python} />
          </dl>
        </Card>
        <Card title="Database">
          <dl className="divide-y divide-line">
            <Row label="Status" value={<Badge tone="up">Connected</Badge>} />
            <Row label="Latency" value={`${h.database.latency_ms} ms`} />
            <Row label="Size" value={formatBytes(h.database.size_bytes)} />
            <Row label="Connections" value={`${h.database.connections} / ${h.database.max_connections}`} />
            <Row label="Server" value={h.database.version} />
          </dl>
        </Card>
        <Card title="Server">
          <dl className="divide-y divide-line">
            <Row label="Disk used" value={disk ? `${formatBytes(disk.used_bytes)} of ${formatBytes(disk.total_bytes)} (${diskPct}%)` : "—"} />
            <Row label="Free" value={disk ? formatBytes(disk.free_bytes) : "—"} />
            <Row label="CPUs" value={h.server.cpu_count ?? "—"} />
            <Row label="Load (1/5/15 min)" value={h.server.load_average ? h.server.load_average.map((l) => l.toFixed(2)).join(" / ") : "n/a"} />
          </dl>
          {diskPct != null && (
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-ink-700">
              <div className={diskPct > 85 ? "h-full bg-down" : diskPct > 70 ? "h-full bg-warn" : "h-full bg-up"} style={{ width: `${diskPct}%` }} />
            </div>
          )}
        </Card>
      </div>

      <section className="card mt-4 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-4">
          <h2 className="font-semibold">Monitoring workers</h2>
          <span className="text-xs text-fg-subtle">
            {h.scheduler.overdue_monitors ? (
              <span className="inline-flex items-center gap-1 text-warn"><AlertTriangle className="h-3.5 w-3.5" /> {h.scheduler.overdue_monitors} overdue (max {h.scheduler.max_delay_seconds} s)</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-up"><CheckCircle2 className="h-3.5 w-3.5" /> schedule on time</span>
            )}
          </span>
        </div>
        {h.workers.length === 0 ? (
          <p className="px-5 py-6 text-sm text-fg-muted">No worker has reported yet. Start one with <code className="rounded bg-ink-700 px-1.5 py-0.5">python -m app.worker</code>.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs text-fg-subtle">
                <tr><th className="px-5 py-2 font-medium">Worker</th><th className="px-2 py-2 font-medium">Status</th><th className="px-2 py-2 text-right font-medium">Checks</th><th className="px-2 py-2 text-right font-medium">Failed</th><th className="px-2 py-2 text-right font-medium">In flight</th><th className="px-5 py-2 text-right font-medium">Last seen</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {h.workers.map((w) => (
                  <tr key={w.worker_id}>
                    <td className="px-5 py-2.5"><p className="font-medium">{w.worker_id}</p><p className="text-xs text-fg-subtle">v{w.version} · since {timeAgo(w.started_at)}</p></td>
                    <td className="px-2 py-2.5">{w.alive ? <Badge tone="up">Running</Badge> : <Badge tone="down">Stale</Badge>}</td>
                    <td className="tnum px-2 py-2.5 text-right">{formatNumber(w.checks_total)}</td>
                    <td className="tnum px-2 py-2.5 text-right">{formatNumber(w.checks_failed)}</td>
                    <td className="tnum px-2 py-2.5 text-right">{w.in_flight}</td>
                    <td className="px-5 py-2.5 text-right text-fg-muted">{timeAgo(w.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {h.workers.some((w) => !w.alive) && (
          <p className="border-t border-line px-5 py-3 text-xs text-fg-subtle">
            Stale entries come from workers that stopped without shutting down cleanly; they are removed automatically after 24 hours.
          </p>
        )}
      </section>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Email delivery">
          <dl className="divide-y divide-line">
            <Row label="SMTP" value={h.email.smtp_configured ? h.email.smtp_host : <Badge tone="down">Not configured</Badge>} />
            <Row label="Queued" value={h.email.queued} />
            <Row label="Oldest queued" value={h.email.queued ? formatDuration(h.email.oldest_seconds) : "—"} />
          </dl>
        </Card>
        <Card title="Largest tables">
          <dl className="divide-y divide-line">
            {h.database.largest_tables.map((t) => (
              <Row key={t.name} label={t.name} value={`${formatNumber(t.rows)} rows · ${formatBytes(t.bytes)}`} />
            ))}
          </dl>
        </Card>
      </div>

      <RuntimeSettings />
    </>
  );
}

type SettingsPayload = { values: { public_signup: boolean }; notes: Record<string, string>; edition: string };

function RuntimeSettings() {
  const { data, setData } = useApi<SettingsPayload>("/api/admin/settings");
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  if (!data) return null;

  async function set(value: boolean) {
    if (!data) return;
    setData({ ...data, values: { ...data.values, public_signup: value } });
    try {
      await api("/api/admin/settings", { method: "PUT", body: { public_signup: value } });
      setMsg({ tone: "success", text: "Saved." });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Saving failed." });
    }
  }

  return (
    <section className="card mt-4 p-5">
      <h2 className="font-semibold">Settings</h2>
      {msg && <Alert tone={msg.tone} className="mt-3">{msg.text}</Alert>}
      <div className="mt-2">
        <Toggle label="Open sign-up" description={data.notes.public_signup}
          checked={data.values.public_signup} disabled={data.edition === "hosted"} onChange={set} />
      </div>
      <p className="mt-2 text-xs text-fg-subtle">Secrets (database, SMTP password, secret key) are configured through environment variables and are never shown here.</p>
    </section>
  );
}
