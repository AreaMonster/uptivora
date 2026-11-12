"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ExternalLink, Pause, Pencil, Play, Trash2 } from "lucide-react";
import { ResponseTimeChart, UptimeBars } from "@/components/app/charts";
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  ConfirmDialog,
  Skeleton,
  StatusPill,
} from "@/components/ui";
import { ApiError, api, type Incident, type Monitor, type SeriesPoint } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  cn,
  daysUntil,
  formatDateTime,
  formatDuration,
  formatInterval,
  formatMs,
  formatUptime,
  timeAgo,
} from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Detail = { monitor: Monitor; uptime: Record<"24h" | "7d" | "30d" | "90d", number | null> };
type Check = {
  checked_at: string;
  is_up: boolean;
  status_code: number | null;
  response_ms: number | null;
  error_kind: string | null;
  error: string | null;
};
const RANGES = ["24h", "7d", "30d", "90d"] as const;

export function MonitorDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, refresh } = useAuth();
  const [range, setRange] = useState<(typeof RANGES)[number]>("24h");
  const detail = useApi<Detail>(`/api/monitors/${id}`, { refreshMs: 30_000 });
  const series = useApi<{ points: SeriesPoint[] }>(`/api/monitors/${id}/series?range=${range}`, {
    refreshMs: 60_000,
  });
  const checks = useApi<Check[]>(`/api/monitors/${id}/checks?limit=15`, { refreshMs: 30_000 });
  const incidents = useApi<Incident[]>(`/api/monitors/${id}/incidents?limit=20`);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (detail.error) {
    return (
      <Alert tone="error" title={detail.error.status === 404 ? "Monitor not found" : "Could not load monitor"}>
        {detail.error.status === 404 ? "It may have been deleted." : detail.error.message}{" "}
        <Link href="/dashboard" className="underline">Back to monitors</Link>
      </Alert>
    );
  }
  if (!detail.data) return <Skeleton className="h-[480px]" />;
  const { monitor: m, uptime } = detail.data;
  const sslDays = daysUntil(m.ssl_expires_at);
  const tz = me?.user.timezone;

  async function act(path: "pause" | "resume") {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api<Monitor>(`/api/monitors/${m.id}/${path}`, { method: "POST" });
      detail.setData({ monitor: updated, uptime });
      void refresh();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api(`/api/monitors/${m.id}`, { method: "DELETE" });
      void refresh();
      router.replace("/dashboard");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Delete failed.");
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  return (
    <>
      <Link href="/dashboard" className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
        <ArrowLeft className="h-4 w-4" /> Monitors
      </Link>

      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{m.name}</h1>
            <StatusPill status={m.status} />
          </div>
          <a href={m.url} target="_blank" rel="noopener noreferrer nofollow"
            className="mt-1 inline-flex max-w-full items-center gap-1.5 truncate text-sm text-fg-muted hover:text-accent">
            <span className="truncate">{m.url}</span> <ExternalLink className="h-3.5 w-3.5 shrink-0" />
          </a>
          <p className="mt-1 text-xs text-fg-subtle">
            {m.method} every {formatInterval(m.interval_seconds)} · timeout {m.timeout_seconds}s ·
            expects {m.expected_status}
            {m.keyword && <> · keyword “{m.keyword}”</>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {m.is_paused ? (
            <Button variant="secondary" onClick={() => act("resume")} loading={busy}>
              <Play className="h-4 w-4" /> Resume
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => act("pause")} loading={busy}>
              <Pause className="h-4 w-4" /> Pause
            </Button>
          )}
          <ButtonLink href={`/monitors/${m.id}/edit`} variant="secondary">
            <Pencil className="h-4 w-4" /> Edit
          </ButtonLink>
          <Button variant="danger" onClick={() => setConfirmDelete(true)} aria-label="Delete monitor">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {actionError && <Alert tone="error" className="mb-6">{actionError}</Alert>}
      {m.paused_reason === "plan_limit" && (
        <Alert tone="warning" className="mb-6">
          This monitor was paused because your plan’s monitor limit was reduced.
        </Alert>
      )}
      {m.status === "pending" && !m.is_paused && (
        <Alert tone="info" className="mb-6">Waiting for the first check — results appear here within a minute.</Alert>
      )}
      {m.status === "down" && m.last_error && (
        <Alert tone="error" title="Currently down" className="mb-6">{m.last_error}</Alert>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {RANGES.map((r) => (
          <div key={r} className="card px-4 py-3.5">
            <p className="text-xs text-fg-subtle">Uptime {r}</p>
            <p className="tnum mt-1 text-xl font-semibold">{formatUptime(uptime[r])}</p>
          </div>
        ))}
        <div className="card px-4 py-3.5">
          <p className="text-xs text-fg-subtle">Last response</p>
          <p className="tnum mt-1 text-xl font-semibold">{formatMs(m.last_response_ms)}</p>
          <p className="mt-0.5 text-[11px] text-fg-subtle">{timeAgo(m.last_checked_at)}</p>
        </div>
        <div className="card px-4 py-3.5">
          <p className="text-xs text-fg-subtle">SSL certificate</p>
          <p className={cn("tnum mt-1 text-xl font-semibold",
            sslDays != null && sslDays <= m.ssl_warning_days && "text-warn",
            sslDays != null && sslDays < 0 && "text-down")}>
            {!m.ssl_check_enabled || !m.url.startsWith("https") ? "—"
              : sslDays == null ? "Pending" : sslDays < 0 ? "Expired" : `${sslDays} days`}
          </p>
          {m.ssl_issuer && <p className="mt-0.5 truncate text-[11px] text-fg-subtle">{m.ssl_issuer}</p>}
        </div>
      </div>

      <section className="card mt-6 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-semibold">Response time & availability</h2>
          <div className="inline-flex rounded-lg border border-line bg-ink-900 p-0.5" role="tablist">
            {RANGES.map((r) => (
              <button key={r} type="button" role="tab" aria-selected={range === r}
                onClick={() => setRange(r)}
                className={cn("rounded-md px-3 py-1 text-xs font-medium",
                  range === r ? "bg-ink-700 text-fg" : "text-fg-muted hover:text-fg")}>
                {r}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-5">
          {series.data ? (
            <>
              <ResponseTimeChart points={series.data.points} range={range} />
              <UptimeBars points={series.data.points} className="mt-5" />
            </>
          ) : (
            <Skeleton className="h-72" />
          )}
        </div>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="card overflow-hidden">
          <h2 className="border-b border-line px-5 py-4 font-semibold">Recent checks</h2>
          {checks.data && checks.data.length === 0 && (
            <p className="px-5 py-6 text-sm text-fg-subtle">No checks yet.</p>
          )}
          <ul className="divide-y divide-line">
            {checks.data?.map((c) => (
              <li key={c.checked_at} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
                <span className="flex min-w-0 items-center gap-2.5">
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", c.is_up ? "bg-up" : "bg-down")} />
                  <span className="truncate text-fg-muted">
                    {formatDateTime(c.checked_at, tz)}
                  </span>
                </span>
                <span className="tnum truncate text-right text-xs">
                  {c.is_up ? (
                    <>{c.status_code} · {formatMs(c.response_ms)}</>
                  ) : (
                    <span className="text-[#fda4af]" title={c.error ?? undefined}>
                      {c.status_code ?? c.error_kind ?? "failed"}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="card overflow-hidden">
          <h2 className="border-b border-line px-5 py-4 font-semibold">Incidents</h2>
          {incidents.data && incidents.data.length === 0 && (
            <p className="px-5 py-6 text-sm text-fg-subtle">No incidents recorded. </p>
          )}
          <ul className="divide-y divide-line">
            {incidents.data?.map((i) => (
              <li key={i.id} className="px-5 py-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{formatDateTime(i.started_at, tz)}</span>
                  {i.resolved_at ? (
                    <Badge tone="up">Resolved</Badge>
                  ) : (
                    <Badge tone="down">Ongoing</Badge>
                  )}
                </div>
                <p className="mt-1 text-xs text-fg-muted">
                  {i.cause || "Unreachable"} · lasted {formatDuration(i.duration_seconds)}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete “${m.name}”?`}
        confirmLabel="Delete monitor"
        loading={busy}
        onConfirm={remove}
        onCancel={() => setConfirmDelete(false)}
      >
        All check results and incident history for this monitor are permanently deleted. This
        cannot be undone. Consider pausing it instead.
      </ConfirmDialog>
    </>
  );
}
