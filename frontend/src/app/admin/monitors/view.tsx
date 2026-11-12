"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Alert, Badge, Button, ConfirmDialog, PageHeader, Skeleton, StatusPill, TextField } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { AdminMonitorRow, Paged } from "@/lib/admin-types";
import { cn, formatInterval, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "down", label: "Down" },
  { key: "paused", label: "Paused" },
  { key: "admin_paused", label: "Paused by admin" },
] as const;

export function MonitorsView() {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [page, setPage] = useState(1);
  const [target, setTarget] = useState<AdminMonitorRow | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const id = setTimeout(() => { setQ(input.trim()); setPage(1); }, 300);
    return () => clearTimeout(id);
  }, [input]);

  const params = new URLSearchParams({ status, page: String(page), page_size: "50" });
  if (q) params.set("q", q);
  const { data, error, reload } = useApi<Paged<AdminMonitorRow>>(`/api/admin/monitors?${params}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  async function pause() {
    if (!target) return;
    setBusy(target.id);
    try {
      await api(`/api/admin/monitors/${target.id}/pause`, { method: "POST", body: { reason } });
      setMsg({ tone: "success", text: `“${target.name}” paused. The owner cannot resume it.` });
      await reload();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Pause failed." });
    } finally {
      setBusy(null);
      setTarget(null);
      setReason("");
    }
  }

  async function resume(m: AdminMonitorRow) {
    setBusy(m.id);
    try {
      await api(`/api/admin/monitors/${m.id}/resume`, { method: "POST" });
      setMsg({ tone: "success", text: `“${m.name}” resumed.` });
      await reload();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Resume failed." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Monitors" description="All monitors of all customers. Pause monitors that cause abuse or excessive load." />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <label className="relative flex-1">
          <span className="sr-only">Search monitors</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-subtle" />
          <input className="input pl-9" placeholder="Search URL, name or owner email" value={input}
            onChange={(e) => setInput(e.target.value)} />
        </label>
        <div className="inline-flex flex-wrap rounded-lg border border-line bg-ink-900 p-0.5" role="tablist">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={status === f.key}
              onClick={() => { setStatus(f.key); setPage(1); }}
              className={cn("rounded-md px-3 py-1.5 text-sm font-medium",
                status === f.key ? "bg-ink-700 text-fg" : "text-fg-muted hover:text-fg")}>
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      {error && <Alert tone="error">{error.message}</Alert>}
      {!data && !error && <Skeleton className="h-96" />}
      {data && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b border-line text-left text-xs text-fg-subtle">
                <tr>
                  <th className="px-5 py-3 font-medium">Monitor</th>
                  <th className="px-2 py-3 font-medium">Owner</th>
                  <th className="px-2 py-3 font-medium">Status</th>
                  <th className="hidden px-2 py-3 font-medium xl:table-cell">Interval</th>
                  <th className="hidden px-2 py-3 font-medium xl:table-cell">Last check</th>
                  <th className="px-5 py-3 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((m) => (
                  <tr key={m.id}>
                    <td className="max-w-[280px] px-5 py-3">
                      <p className="truncate font-medium">{m.name}</p>
                      <p className="truncate text-xs text-fg-subtle" title={m.url}>{m.url}</p>
                    </td>
                    <td className="max-w-[200px] truncate px-2 py-3">
                      <Link href={`/admin/users/${m.owner_id}`} className="text-fg-muted hover:text-accent">{m.owner_email}</Link>
                    </td>
                    <td className="px-2 py-3">
                      <span className="flex items-center gap-1.5">
                        <StatusPill status={m.status} />
                        {m.paused_reason === "admin" && <Badge tone="warn">Admin</Badge>}
                      </span>
                    </td>
                    <td className="hidden whitespace-nowrap px-2 py-3 text-fg-muted xl:table-cell">{formatInterval(m.interval_seconds)}</td>
                    <td className="hidden whitespace-nowrap px-2 py-3 text-fg-muted xl:table-cell">{m.last_checked_at ? timeAgo(m.last_checked_at) : "never"}</td>
                    <td className="whitespace-nowrap px-5 py-3 text-right">
                      {m.paused_reason === "admin" ? (
                        <Button size="sm" variant="secondary" loading={busy === m.id} onClick={() => resume(m)}>Resume</Button>
                      ) : !m.is_paused ? (
                        <Button size="sm" variant="danger" onClick={() => setTarget(m)}>Pause</Button>
                      ) : (
                        <span className="text-xs text-fg-subtle">paused by owner</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.items.length === 0 && <p className="px-5 py-8 text-center text-sm text-fg-subtle">No monitors match.</p>}
          {pages > 1 && (
            <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm">
              <span className="text-fg-muted">Page {page} of {pages} · {data.total} monitors</span>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
                <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      )}
      <ConfirmDialog open={target !== null} title={`Pause “${target?.name ?? ""}”?`} confirmLabel="Pause monitor"
        loading={busy === target?.id} onConfirm={pause} onCancel={() => { setTarget(null); setReason(""); }}>
        <p>Checks stop immediately. The owner sees that an administrator paused it and cannot resume it.</p>
        <div className="mt-4">
          <TextField label="Reason (internal, recorded in the audit log)" value={reason} maxLength={500}
            onChange={(e) => setReason(e.target.value)} />
        </div>
      </ConfirmDialog>
    </>
  );
}
