"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Alert, Badge, Button, ConfirmDialog, SelectField, Skeleton, StatusPill } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { AdminPlan, AdminUserDetail } from "@/lib/admin-types";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatInterval, hostOf, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Action = { key: string; title: string; text: string; confirm: string; run: () => Promise<unknown>; tone: "danger" | "primary" };

export function UserDetailView() {
  const { id } = useParams<{ id: string }>();
  const { me } = useAuth();
  const { data, error, reload } = useApi<AdminUserDetail>(`/api/admin/users/${id}`);
  const [pending, setPending] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  if (error) return <Alert tone="error">{error.status === 404 ? "User not found." : error.message}</Alert>;
  if (!data) return <Skeleton className="h-96" />;
  const u = data.user;
  const self = me?.user.id === u.id;

  async function execute() {
    if (!pending) return;
    setBusy(true);
    try {
      await pending.run();
      setMsg({ tone: "success", text: `${pending.title} — done.` });
      await reload();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Action failed." });
    } finally {
      setBusy(false);
      setPending(null);
    }
  }

  const patch = (body: Record<string, unknown>) => api(`/api/admin/users/${u.id}`, { method: "PATCH", body });
  const actions: Action[] = [
    u.is_active
      ? { key: "suspend", title: "Suspend account", tone: "danger", confirm: "Suspend",
          text: "The user is signed out everywhere and cannot sign in. Their monitors stop being checked. Data is kept.",
          run: () => patch({ is_active: false }) }
      : { key: "reactivate", title: "Reactivate account", tone: "primary", confirm: "Reactivate",
          text: "The user can sign in again and their monitors resume.", run: () => patch({ is_active: true }) },
    u.role === "admin"
      ? { key: "demote", title: "Remove admin rights", tone: "danger", confirm: "Remove rights",
          text: "The user loses access to the admin area.", run: () => patch({ role: "user" }) }
      : { key: "promote", title: "Make administrator", tone: "primary", confirm: "Make admin",
          text: "Administrators can see all customers, edit plans and suspend accounts.", run: () => patch({ role: "admin" }) },
    { key: "sessions", title: "Sign out all sessions", tone: "danger", confirm: "Sign out",
      text: "All of the user's active sessions end immediately.",
      run: () => api(`/api/admin/users/${u.id}/revoke-sessions`, { method: "POST" }) },
  ];

  return (
    <>
      <Link href="/admin/users" className="mb-4 inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg">
        <ArrowLeft className="h-4 w-4" /> Users
      </Link>
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{u.email}</h1>
            {u.is_active ? <Badge tone="up">Active</Badge> : <Badge tone="down">Suspended</Badge>}
            {u.role === "admin" && <Badge tone="warn">Admin</Badge>}
            {!u.email_verified && <Badge>Email not confirmed</Badge>}
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            {u.full_name || "No name"} · joined {formatDateTime(u.created_at)} · last login {u.last_login_at ? timeAgo(u.last_login_at) : "never"} · {data.timezone}
          </p>
        </div>
        {!self && (
          <div className="flex flex-wrap gap-2">
            {actions.map((a) => (
              <Button key={a.key} size="sm" variant={a.tone === "danger" ? "danger" : "secondary"} onClick={() => setPending(a)}>
                {a.title}
              </Button>
            ))}
          </div>
        )}
      </div>
      {self && <Alert tone="info" className="mb-6">This is your own account — manage it in your personal settings.</Alert>}
      {msg && <Alert tone={msg.tone} className="mb-6">{msg.text}</Alert>}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card p-5">
          <h2 className="font-semibold">Subscription</h2>
          {data.subscription ? (
            <dl className="mt-3 space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-fg-muted">Plan</dt><dd>{data.subscription.plan} {data.subscription.is_test && <Badge tone="warn">Test</Badge>}</dd></div>
              <div className="flex justify-between"><dt className="text-fg-muted">Status</dt><dd>{data.subscription.status}</dd></div>
              <div className="flex justify-between"><dt className="text-fg-muted">Renews</dt><dd>{formatDateTime(data.subscription.current_period_end)}</dd></div>
              <div className="flex justify-between"><dt className="text-fg-muted">Provider</dt><dd>{data.subscription.provider}</dd></div>
            </dl>
          ) : <p className="mt-3 text-sm text-fg-muted">No active subscription.</p>}
          {data.limits.scope === "user" && <AssignPlan userId={u.id} onDone={async () => {
            setMsg({ tone: "success", text: "Plan assigned." });
            await reload();
          }} />}
        </section>
        <section className="card p-5">
          <h2 className="font-semibold">Limits & usage</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-fg-muted">Source</dt><dd>{data.limits.source}</dd></div>
            <div className="flex justify-between"><dt className="text-fg-muted">Active monitors</dt><dd className="tnum">{data.usage.active_monitors} / {data.limits.max_monitors ?? "∞"}</dd></div>
            <div className="flex justify-between"><dt className="text-fg-muted">Fastest interval</dt><dd>{formatInterval(data.limits.min_interval_seconds)}</dd></div>
            <div className="flex justify-between"><dt className="text-fg-muted">Open incidents</dt><dd className="tnum">{data.usage.open_incidents}</dd></div>
          </dl>
        </section>
        <section className="card p-5">
          <h2 className="font-semibold">Recent activity</h2>
          <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto text-sm">
            {data.audit.length === 0 && <li className="text-fg-subtle">No recorded activity.</li>}
            {data.audit.map((a, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="truncate">{a.action}{!a.by_self && <span className="text-warn"> (by admin)</span>}</span>
                <span className="shrink-0 text-xs text-fg-subtle">{timeAgo(a.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="card mt-4 overflow-hidden">
        <h2 className="border-b border-line px-5 py-4 font-semibold">Monitors ({data.monitors.length})</h2>
        {data.monitors.length === 0 && <p className="px-5 py-6 text-sm text-fg-subtle">No monitors.</p>}
        <ul className="divide-y divide-line">
          {data.monitors.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium">{m.name}</p>
                <p className="truncate text-xs text-fg-subtle">{hostOf(m.url)} · every {formatInterval(m.interval_seconds)} · {m.last_checked_at ? `checked ${timeAgo(m.last_checked_at)}` : "never checked"}</p>
              </div>
              <span className="flex items-center gap-2">
                {m.paused_reason === "admin" && <Badge tone="warn">Paused by admin</Badge>}
                <StatusPill status={m.status} />
              </span>
            </li>
          ))}
        </ul>
      </section>
      <p className="mt-4 text-xs text-fg-subtle">Read-only support view. Administrators cannot sign in as a customer.</p>

      <ConfirmDialog open={pending !== null} title={pending?.title ?? ""} confirmLabel={pending?.confirm ?? ""}
        tone={pending?.tone} loading={busy} onConfirm={execute} onCancel={() => setPending(null)}>
        {pending?.text}
      </ConfirmDialog>
    </>
  );
}

function AssignPlan({ userId, onDone }: { userId: string; onDone: () => Promise<void> }) {
  const { data: plans } = useApi<AdminPlan[]>("/api/admin/plans");
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState("");
  const [months, setMonths] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!plans) return null;

  async function assign() {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/admin/users/${userId}/subscription`, {
        method: "POST", body: { plan_code: plan || plans?.[0]?.code, months },
      });
      setOpen(false);
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not assign the plan.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="ghost" className="mt-3 px-0" onClick={() => setOpen(true)}>Assign plan…</Button>
      <ConfirmDialog open={open} tone="primary" title="Assign a plan without payment" confirmLabel="Assign plan"
        loading={busy} onConfirm={assign} onCancel={() => setOpen(false)}>
        <p>For complimentary accounts or customers invoiced outside Uptivora. It replaces any current subscription and ends automatically.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <SelectField label="Plan" value={plan || plans[0]?.code} onChange={(e) => setPlan(e.target.value)}>
            {plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
          </SelectField>
          <SelectField label="Duration" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {[1, 3, 6, 12, 24].map((m) => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""}</option>)}
          </SelectField>
        </div>
        {error && <p className="mt-3 text-xs text-down-ink">{error}</p>}
      </ConfirmDialog>
    </>
  );
}
