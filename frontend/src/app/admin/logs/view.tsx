"use client";

import { useState } from "react";
import { Alert, Badge, PageHeader, Skeleton } from "@/components/ui";
import type { AuditRow, SystemEventRow } from "@/lib/admin-types";
import { cn, formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const TABS = [
  { key: "app", label: "Application log" },
  { key: "audit", label: "Audit log" },
] as const;
const LEVELS = ["all", "info", "warning", "error"] as const;

function levelTone(level: string): "neutral" | "warn" | "down" | "accent" {
  if (level === "error" || level === "critical") return "down";
  if (level === "warning") return "warn";
  if (level === "info") return "accent";
  return "neutral";
}

export function LogsView() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("app");
  return (
    <>
      <PageHeader title="Logs" description="Operational events from the API and workers, and every security-relevant action." />
      <div className="mb-4 inline-flex rounded-[3px] border border-line bg-sunken p-0.5" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={cn("rounded-[3px] px-3 py-1.5 text-sm font-medium", tab === t.key ? "bg-muted text-fg" : "text-fg-muted hover:text-fg")}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "app" ? <AppLog /> : <AuditLog />}
    </>
  );
}

function AppLog() {
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("all");
  const { data, error } = useApi<SystemEventRow[]>(`/api/admin/logs?level=${level}&limit=200`, { refreshMs: 20_000 });
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {LEVELS.map((l) => (
          <button key={l} type="button" onClick={() => setLevel(l)}
            className={cn("rounded-[3px] border px-2.5 py-1 text-xs font-medium capitalize",
              level === l ? "border-line-strong bg-muted text-fg" : "border-line text-fg-muted hover:text-fg")}>
            {l === "warning" ? "warnings & errors" : l}
          </button>
        ))}
      </div>
      {error && <Alert tone="error">{error.message}</Alert>}
      {!data && !error && <Skeleton className="h-96" />}
      {data && data.length === 0 && <p className="card p-6 text-sm text-fg-muted">No events.</p>}
      {data && data.length > 0 && (
        <ul className="card divide-y divide-line overflow-hidden">
          {data.map((e) => (
            <li key={e.id} className="px-5 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={levelTone(e.level)}>{e.level}</Badge>
                <span className="font-mono text-xs text-fg-subtle">{e.source}</span>
                <span className="ml-auto text-xs text-fg-subtle">{formatDateTime(e.created_at)}</span>
              </div>
              <p className="mt-1.5 break-words">{e.message}</p>
              {typeof e.details?.exception === "string" && (
                <p className="mt-1 break-words font-mono text-xs text-down-ink">{e.details.exception}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function AuditLog() {
  const [action, setAction] = useState("");
  const params = new URLSearchParams({ limit: "200" });
  if (action) params.set("action", action);
  const { data, error } = useApi<AuditRow[]>(`/api/admin/audit?${params}`);
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {[["", "All"], ["admin.", "Admin actions"], ["auth.", "Sign-ins"], ["user.", "Accounts"], ["monitor.", "Monitors"]].map(([v, l]) => (
          <button key={v} type="button" onClick={() => setAction(v)}
            className={cn("rounded-[3px] border px-2.5 py-1 text-xs font-medium",
              action === v ? "border-line-strong bg-muted text-fg" : "border-line text-fg-muted hover:text-fg")}>
            {l}
          </button>
        ))}
      </div>
      {error && <Alert tone="error">{error.message}</Alert>}
      {!data && !error && <Skeleton className="h-96" />}
      {data && (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="border-b border-line text-left text-xs text-fg-subtle">
              <tr><th className="px-5 py-3 font-medium">When</th><th className="px-2 py-3 font-medium">Action</th><th className="px-2 py-3 font-medium">Actor</th><th className="px-2 py-3 font-medium">Target</th><th className="px-5 py-3 font-medium">IP</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((a) => (
                <tr key={a.id} className="align-top">
                  <td className="whitespace-nowrap px-5 py-2.5 text-fg-muted">{formatDateTime(a.created_at)}</td>
                  <td className="px-2 py-2.5">
                    <span className={cn("font-mono text-xs", a.action.startsWith("admin.") && "text-warn",
                      a.action === "auth.login_failed" && "text-down-ink")}>{a.action}</span>
                    {Object.keys(a.details ?? {}).length > 0 && (
                      <p className="mt-0.5 max-w-[360px] truncate font-mono text-[11px] text-fg-subtle" title={JSON.stringify(a.details)}>
                        {JSON.stringify(a.details)}
                      </p>
                    )}
                  </td>
                  <td className="px-2 py-2.5 text-fg-muted">{a.actor ?? "—"}</td>
                  <td className="px-2 py-2.5 font-mono text-xs text-fg-subtle">{a.target_type ? `${a.target_type}:${(a.target_id ?? "").slice(0, 8)}` : "—"}</td>
                  <td className="px-5 py-2.5 font-mono text-xs text-fg-subtle">{a.ip ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.length === 0 && <p className="px-5 py-6 text-sm text-fg-muted">No entries.</p>}
        </div>
      )}
    </>
  );
}
