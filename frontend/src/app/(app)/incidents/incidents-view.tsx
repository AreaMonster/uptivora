"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCheck, MessageSquareText, ShieldCheck } from "lucide-react";
import { Alert, Badge, Button, EmptyState, PageHeader, Skeleton } from "@/components/ui";
import { ApiError, api, type IncidentItem, type IncidentPage, type IncidentSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDateTime, formatDuration } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "open", label: "Ongoing" },
  { key: "resolved", label: "Resolved" },
] as const;

function Stat({ label, value, tone }: { label: string; value: string; tone?: "down" }) {
  return (
    <div className="border-t border-fg pt-2">
      <p className="text-xs text-fg-subtle">{label}</p>
      <p className={cn("tnum mt-1 font-mono text-2xl font-medium", tone === "down" && "text-down-ink")}>
        {value}
      </p>
    </div>
  );
}

export function IncidentsPage() {
  const { me } = useAuth();
  const tz = me?.user.timezone;
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const summary = useApi<IncidentSummary>("/api/incidents/summary?days=30", { refreshMs: 60_000 });
  const page = useApi<IncidentPage>(`/api/incidents?status=${filter}&limit=50`, { refreshMs: 60_000 });
  const [more, setMore] = useState<{ filter: string; items: IncidentItem[]; next: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const extra = more?.filter === filter ? more : null;
  const items = [...(page.data?.items ?? []), ...(extra?.items ?? [])];
  const next = extra ? extra.next : page.data?.next_before ?? null;

  async function loadMore() {
    if (!next) return;
    setLoadingMore(true);
    try {
      const res = await api<IncidentPage>(
        `/api/incidents?status=${filter}&limit=50&before=${encodeURIComponent(next)}`,
      );
      setMore({ filter, items: [...(extra?.items ?? []), ...res.items], next: res.next_before });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load more incidents.");
    } finally {
      setLoadingMore(false);
    }
  }

  const s = summary.data;
  return (
    <>
      <PageHeader title="Incidents" description="Every confirmed outage across your monitors." />

      <div className="grid grid-cols-2 gap-x-6 gap-y-5 lg:grid-cols-4">
        {s ? (
          <>
            <Stat label="Incidents (30 days)" value={String(s.total)} />
            <Stat label="Ongoing now" value={String(s.open)} tone={s.open ? "down" : undefined} />
            <Stat label="Total downtime (30 days)" value={s.downtime_seconds ? formatDuration(s.downtime_seconds) : "0s"} />
            <Stat label="Mean time to recovery" value={formatDuration(s.mean_time_to_recovery_seconds)} />
          </>
        ) : (
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-20" />)
        )}
      </div>

      <div className="mt-6 inline-flex rounded-[3px] border border-line bg-sunken p-0.5" role="tablist">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" role="tab" aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={cn("rounded-[3px] px-3 py-1.5 text-sm font-medium",
              filter === f.key ? "bg-muted text-fg" : "text-fg-muted hover:text-fg")}>
            {f.label}
          </button>
        ))}
      </div>

      {(page.error || error) && <Alert tone="error" className="mt-4">{page.error?.message ?? error}</Alert>}
      {!page.data && !page.error && <Skeleton className="mt-4 h-64" />}
      {page.data && items.length === 0 && (
        <div className="mt-4">
          <EmptyState icon={<ShieldCheck className="h-5 w-5" />}
            title={filter === "open" ? "Nothing is down right now" : "No incidents"}>
            When a monitor goes down, the outage is recorded here with its duration and cause.
          </EmptyState>
        </div>
      )}
      {items.length > 0 && (
        <div className="card mt-4 overflow-hidden">
          <div className="hidden grid-cols-[1.3fr_1.1fr_1.7fr_100px_120px] gap-4 border-b border-line px-5 py-3 text-xs font-medium text-fg-subtle lg:grid">
            <span>Monitor</span><span>Started</span><span>Cause</span><span>Duration</span><span>Status</span>
          </div>
          <ul className="divide-y divide-line">
            {items.map((i) => (
              <li key={i.id}>
                <Link href={`/incidents/${i.id}`}
                  className="grid gap-1 px-5 py-3.5 text-sm hover:bg-hover/60 lg:grid-cols-[1.3fr_1.1fr_1.7fr_100px_120px] lg:items-center lg:gap-4">
                  <span className="flex min-w-0 items-center gap-2 font-medium">
                    <span className="truncate">{i.monitor_name}</span>
                    {i.note && <MessageSquareText className="h-3.5 w-3.5 shrink-0 text-fg-subtle" aria-label="Has a note" />}
                  </span>
                  <span className="text-fg-muted">{formatDateTime(i.started_at, tz)}</span>
                  <span className="truncate text-fg-muted">{i.cause || "Unreachable"}</span>
                  <span className="tnum">{formatDuration(i.duration_seconds)}</span>
                  <span className="flex flex-wrap gap-1.5">
                    {i.resolved_at ? <Badge tone="up">Resolved</Badge> : <Badge tone="down">Ongoing</Badge>}
                    {i.acknowledged_at && !i.resolved_at && (
                      <span title="Acknowledged"><CheckCheck className="h-4 w-4 text-accent" /></span>
                    )}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {next && (
            <div className="border-t border-line p-3 text-center">
              <Button variant="ghost" size="sm" onClick={loadMore} loading={loadingMore}>Load older incidents</Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
