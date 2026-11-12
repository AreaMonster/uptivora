"use client";

import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { Alert, Badge, EmptyState, PageHeader, Skeleton } from "@/components/ui";
import type { Incident } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatDuration } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export function IncidentsPage() {
  const { me } = useAuth();
  const { data, error } = useApi<Incident[]>("/api/account/incidents?limit=200", { refreshMs: 60_000 });
  const tz = me?.user.timezone;

  return (
    <>
      <PageHeader title="Incidents" description="Every confirmed outage across your monitors." />
      {error && <Alert tone="error">{error.message}</Alert>}
      {!data && !error && <Skeleton className="h-64" />}
      {data && data.length === 0 && (
        <EmptyState icon={<ShieldCheck className="h-5 w-5" />} title="No incidents">
          When a monitor goes down, the outage is recorded here with its duration and cause.
        </EmptyState>
      )}
      {data && data.length > 0 && (
        <div className="card overflow-hidden">
          <div className="hidden grid-cols-[1.4fr_1.2fr_1.6fr_110px_100px] gap-4 border-b border-line px-5 py-3 text-xs font-medium text-fg-subtle md:grid">
            <span>Monitor</span><span>Started</span><span>Cause</span><span>Duration</span><span>Status</span>
          </div>
          <ul className="divide-y divide-line">
            {data.map((i) => (
              <li key={i.id}>
                <Link href={`/monitors/${i.monitor_id}`}
                  className="grid gap-1 px-5 py-3.5 text-sm hover:bg-ink-750/60 md:grid-cols-[1.4fr_1.2fr_1.6fr_110px_100px] md:items-center md:gap-4">
                  <span className="truncate font-medium">{i.monitor_name}</span>
                  <span className="text-fg-muted">{formatDateTime(i.started_at, tz)}</span>
                  <span className="truncate text-fg-muted">{i.cause || "Unreachable"}</span>
                  <span className="tnum">{formatDuration(i.duration_seconds)}</span>
                  <span>{i.resolved_at ? <Badge tone="up">Resolved</Badge> : <Badge tone="down">Ongoing</Badge>}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
