"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useState } from "react";
import {
  AlertOctagon,
  ArrowLeft,
  BellRing,
  CheckCheck,
  CircleCheck,
  ExternalLink,
} from "lucide-react";
import { Alert, Badge, Button, Skeleton } from "@/components/ui";
import { ApiError, api, type IncidentDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDateTime, formatDuration, formatMs } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Event = { at: string; icon: ReactNode; tone: string; title: string; detail?: string };

const NOTIFY_LABEL: Record<string, string> = {
  monitor_down: "Outage alert",
  monitor_up: "Recovery alert",
};

function buildTimeline(d: IncidentDetail): Event[] {
  const i = d.incident;
  const events: Event[] = [
    {
      at: i.started_at,
      icon: <AlertOctagon className="h-4 w-4" />,
      tone: "text-down bg-down-soft ring-down/30",
      title: "Outage started",
      detail: i.cause || "Unreachable",
    },
  ];
  for (const n of d.notifications) {
    events.push({
      at: n.sent_at ?? n.created_at,
      icon: <BellRing className="h-4 w-4" />,
      tone: "text-accent bg-accent-soft ring-accent/30",
      title: `${NOTIFY_LABEL[n.kind] ?? "Email"} ${n.status === "sent" ? "sent" : n.status} to ${n.recipient}`,
      detail: n.last_error ?? undefined,
    });
  }
  if (i.acknowledged_at) {
    events.push({
      at: i.acknowledged_at,
      icon: <CheckCheck className="h-4 w-4" />,
      tone: "text-accent bg-accent-soft ring-accent/30",
      title: `Acknowledged${i.acknowledged_by ? ` by ${i.acknowledged_by}` : ""}`,
    });
  }
  if (i.resolved_at) {
    events.push({
      at: i.resolved_at,
      icon: <CircleCheck className="h-4 w-4" />,
      tone: "text-up bg-up-soft ring-up/30",
      title: "Recovered",
      detail: `Down for ${formatDuration(i.duration_seconds)}`,
    });
  }
  return events.sort((a, b) => a.at.localeCompare(b.at));
}

export function IncidentDetailView() {
  const { id } = useParams<{ id: string }>();
  const { me } = useAuth();
  const tz = me?.user.timezone;
  const { data, error, setData } = useApi<IncidentDetail>(`/api/incidents/${id}`, { refreshMs: 30_000 });
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  if (error) {
    return (
      <Alert tone="error" title={error.status === 404 ? "Incident not found" : "Could not load incident"}>
        <Link href="/incidents" className="underline">Back to incidents</Link>
      </Alert>
    );
  }
  if (!data) return <Skeleton className="h-[480px]" />;
  const i = data.incident;
  const noteValue = note ?? i.note ?? "";

  async function patch(key: string, body: Record<string, unknown>, success: string) {
    if (!data) return;
    setBusy(key);
    setMsg(null);
    try {
      const updated = await api<IncidentDetail["incident"]>(`/api/incidents/${i.id}`, { method: "PATCH", body });
      const ackBy = updated.acknowledged_at ? (i.acknowledged_by ?? me?.user.full_name ?? me?.user.email ?? null) : null;
      setData({ ...data, incident: { ...i, ...updated, acknowledged_by: ackBy } });
      setNote(null);
      setMsg({ tone: "success", text: success });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Saving failed." });
    } finally {
      setBusy(null);
    }
  }

  const failed = data.checks.filter((c) => !c.is_up);
  return (
    <>
      <Link href="/incidents" className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
        <ArrowLeft className="h-4 w-4" /> Incidents
      </Link>

      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {data.monitor.name} {i.resolved_at ? "was down" : "is down"}
            </h1>
            {i.resolved_at ? <Badge tone="up">Resolved</Badge> : <Badge tone="down">Ongoing</Badge>}
            {i.acknowledged_at && <Badge tone="accent">Acknowledged</Badge>}
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            {formatDateTime(i.started_at, tz)}
            {i.resolved_at ? ` – ${formatDateTime(i.resolved_at, tz)}` : " – now"} · {formatDuration(i.duration_seconds)}
          </p>
          <Link href={`/monitors/${data.monitor.id}`}
            className="mt-1 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-accent">
            {data.monitor.url} <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        </div>
        {!i.resolved_at && (
          <Button variant={i.acknowledged_at ? "ghost" : "secondary"} loading={busy === "ack"}
            onClick={() => patch("ack", { acknowledged: !i.acknowledged_at },
              i.acknowledged_at ? "Acknowledgement removed." : "Incident acknowledged.")}>
            <CheckCheck className="h-4 w-4" /> {i.acknowledged_at ? "Remove acknowledgement" : "Acknowledge"}
          </Button>
        )}
      </div>

      {msg && <Alert tone={msg.tone} className="mb-6">{msg.text}</Alert>}

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <section className="card p-6">
          <h2 className="font-semibold">Timeline</h2>
          <ol className="mt-5 space-y-5">
            {buildTimeline(data).map((e, idx) => (
              <li key={`${e.at}-${idx}`} className="relative flex gap-4">
                <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-full ring-1", e.tone)}>{e.icon}</span>
                <div className="min-w-0 pt-1">
                  <p className="text-sm font-medium">{e.title}</p>
                  <p className="text-xs text-fg-subtle">{formatDateTime(e.at, tz)}</p>
                  {e.detail && <p className="mt-1 break-words text-sm text-fg-muted">{e.detail}</p>}
                </div>
              </li>
            ))}
            {!i.resolved_at && (
              <li className="flex gap-4 text-sm text-fg-muted">
                <span className="grid h-8 w-8 shrink-0 place-items-center"><span className="h-2 w-2 animate-pulse rounded-full bg-down" /></span>
                <span className="pt-1.5">Still checking — you’ll get a recovery email when it’s back.</span>
              </li>
            )}
          </ol>
        </section>

        <section className="card p-6">
          <h2 className="font-semibold">Notes</h2>
          <p className="mt-1 text-sm text-fg-muted">Root cause, what was done, follow-ups.</p>
          <textarea value={noteValue} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={6}
            className="input mt-4 resize-y" placeholder="e.g. Hosting provider maintenance, restarted PHP-FPM…" />
          <div className="mt-3 flex items-center justify-between gap-3">
            <span className="text-xs text-fg-subtle">{noteValue.length}/2000</span>
            <Button size="sm" loading={busy === "note"} disabled={note === null || note === (i.note ?? "")}
              onClick={() => patch("note", { note: noteValue }, "Note saved.")}>
              Save note
            </Button>
          </div>
        </section>
      </div>

      <section className="card mt-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-4">
          <h2 className="font-semibold">Checks during the incident</h2>
          <span className="text-xs text-fg-subtle">{failed.length} failed of {data.checks.length} shown</span>
        </div>
        {data.checks.length === 0 ? (
          <p className="px-5 py-6 text-sm text-fg-subtle">No check results in this period (older results may have been archived).</p>
        ) : (
          <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
            {data.checks.map((c) => (
              <li key={c.checked_at} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
                <span className="flex min-w-0 items-center gap-2.5">
                  <span className={cn("h-2 w-2 shrink-0 rounded-full", c.is_up ? "bg-up" : "bg-down")} />
                  <span className="text-fg-muted">{formatDateTime(c.checked_at, tz)}</span>
                </span>
                <span className="tnum min-w-0 truncate text-right text-xs">
                  {c.is_up ? <>{c.status_code} · {formatMs(c.response_ms)}</> : (
                    <span className="text-down-ink">{c.error ?? c.error_kind ?? `HTTP ${c.status_code}`}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
