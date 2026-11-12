"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";
import { Mail, RotateCw, Send, Trash2, UserPlus } from "lucide-react";
import { SettingsSection } from "@/components/app/settings-section";
import { Alert, Badge, Button, Skeleton, TextField, Toggle } from "@/components/ui";
import {
  type AlertContact,
  ApiError,
  api,
  type DeliveryLogEntry,
  type NotificationPrefs,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Msg = { tone: "success" | "error" | "info"; text: string } | null;

export function NotificationSettings() {
  return (
    <>
      <PreferencesSection />
      <RecipientsSection />
      <DeliveryLogSection />
    </>
  );
}

function PreferencesSection() {
  const { data, setData } = useApi<NotificationPrefs>("/api/account/notifications");
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);

  async function save(next: NotificationPrefs) {
    setData(next);
    setBusy(true);
    setMsg(null);
    try {
      setData(await api<NotificationPrefs>("/api/account/notifications", { method: "PUT", body: next }));
      setMsg({ tone: "success", text: "Saved." });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Saving failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <SettingsSection id="notifications" title="Alerts"
      description="Which events send an email. Account and security emails are always sent.">
      {!data ? <Skeleton className="h-48" /> : (
        <div className="space-y-3">
          {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
          <div className="divide-y divide-line">
            <Toggle label="Outage alerts" description="Once, when a monitor is confirmed down."
              checked={data.notify_down} disabled={busy}
              onChange={(v) => save({ ...data, notify_down: v })} />
            <Toggle label="Recovery alerts" description="Once, when it is back up — with the outage duration."
              checked={data.notify_recovery} disabled={busy}
              onChange={(v) => save({ ...data, notify_recovery: v })} />
            <Toggle label="SSL certificate warnings"
              description={`When a certificate expires within ${data.ssl_warning_days} days, again at 7 and 1 day, and on expiry.`}
              checked={data.notify_ssl} disabled={busy}
              onChange={(v) => save({ ...data, notify_ssl: v })} />
          </div>
          <p className="text-xs text-fg-subtle">
            Each monitor can also be muted individually in its settings. Monitors that go down and
            up more than 5 times within an hour stop emailing until they settle.
          </p>
        </div>
      )}
    </SettingsSection>
  );
}

function RecipientsSection() {
  const { me } = useAuth();
  const prefs = useApi<NotificationPrefs>("/api/account/notifications");
  const contacts = useApi<AlertContact[]>("/api/account/alert-contacts");
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (!me) return null;
  const verified = me.user.email_verified;

  async function run(key: string, fn: () => Promise<unknown>, success?: string) {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
      if (success) setMsg({ tone: "success", text: success });
      await contacts.reload();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Request failed." });
    } finally {
      setBusy(null);
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    setFieldError(undefined);
    setBusy("add");
    setMsg(null);
    try {
      const created = await api<AlertContact>("/api/account/alert-contacts", {
        method: "POST", body: { email },
      });
      setEmail("");
      setMsg({ tone: "info", text: `We sent a confirmation link to ${created.email}. Alerts start once it is confirmed.` });
      await contacts.reload();
    } catch (err) {
      if (err instanceof ApiError && err.fields.email) setFieldError(err.fields.email);
      else setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Could not add contact." });
    } finally {
      setBusy(null);
    }
  }

  async function toggleAccount(value: boolean) {
    if (!prefs.data) return;
    const next = { ...prefs.data, send_to_account_email: value };
    prefs.setData(next);
    await run("account", () => api("/api/account/notifications", { method: "PUT", body: next }));
  }

  async function sendTest() {
    setBusy("test");
    setMsg(null);
    try {
      const res = await api<{ recipients: string[] }>("/api/account/notifications/test", { method: "POST" });
      setMsg({ tone: "success", text: `Test alert queued for ${res.recipients.join(", ")}. It should arrive within a minute.` });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Could not send test alert." });
    } finally {
      setBusy(null);
    }
  }

  const list = contacts.data ?? [];
  return (
    <SettingsSection title="Recipients"
      description="Alerts go to your account email and to up to 5 extra addresses, e.g. a team inbox. Every address must confirm first.">
      <div className="space-y-5">
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

        <div className="flex items-center justify-between gap-4 rounded-xl border border-line bg-ink-850 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <Mail className="h-4 w-4 shrink-0 text-fg-subtle" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{me.user.email}</p>
              <p className="text-xs text-fg-subtle">
                Account email · {verified ? "confirmed" : "not confirmed — alerts are held back"}
              </p>
            </div>
          </div>
          {prefs.data && (
            <Toggle label="" ariaLabel="Send alerts to my account email" checked={prefs.data.send_to_account_email}
              disabled={busy === "account"} onChange={toggleAccount} />
          )}
        </div>

        {contacts.loading ? <Skeleton className="h-16" /> : list.length > 0 && (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {list.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className={cn("truncate text-sm font-medium", !c.is_enabled && "text-fg-subtle line-through")}>
                    {c.email}
                  </p>
                  <div className="mt-1 flex gap-2">
                    {c.status === "confirmed" ? <Badge tone="up">Confirmed</Badge> : <Badge tone="warn">Waiting for confirmation</Badge>}
                    {!c.is_enabled && <Badge>Paused</Badge>}
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {c.status === "pending" && (
                    <Button size="sm" variant="ghost" loading={busy === `resend-${c.id}`}
                      onClick={() => run(`resend-${c.id}`,
                        () => api(`/api/account/alert-contacts/${c.id}/resend`, { method: "POST" }),
                        `Confirmation email sent again to ${c.email}.`)}>
                      <RotateCw className="h-3.5 w-3.5" /> Resend
                    </Button>
                  )}
                  {c.status === "confirmed" && (
                    <Toggle label="" ariaLabel={`Send alerts to ${c.email}`} checked={c.is_enabled} disabled={busy === `toggle-${c.id}`}
                      onChange={(v) => run(`toggle-${c.id}`,
                        () => api(`/api/account/alert-contacts/${c.id}`, { method: "PATCH", body: { is_enabled: v } }))} />
                  )}
                  <Button size="sm" variant="ghost" aria-label={`Remove ${c.email}`}
                    loading={busy === `delete-${c.id}`}
                    onClick={() => run(`delete-${c.id}`,
                      () => api(`/api/account/alert-contacts/${c.id}`, { method: "DELETE" }))}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {list.length < 5 && (
          <form onSubmit={add} className="flex flex-col gap-3 sm:flex-row sm:items-start">
            <TextField label="Add a recipient" type="email" placeholder="team@example.com"
              className="flex-1" value={email} error={fieldError}
              onChange={(e) => setEmail(e.target.value)} />
            <Button type="submit" variant="secondary" className="sm:mt-[26px]" loading={busy === "add"}
              disabled={!email}>
              <UserPlus className="h-4 w-4" /> Add
            </Button>
          </form>
        )}

        <div className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-fg-muted">Check that alerts arrive (and don’t land in spam).</p>
          <Button variant="secondary" onClick={sendTest} loading={busy === "test"}>
            <Send className="h-4 w-4" /> Send test alert
          </Button>
        </div>
      </div>
    </SettingsSection>
  );
}

const KIND_LABEL: Record<DeliveryLogEntry["kind"], string> = {
  monitor_down: "Outage",
  monitor_up: "Recovery",
  ssl_expiring: "SSL warning",
  ssl_error: "SSL error",
  test: "Test",
};

const STATUS_TONE: Record<DeliveryLogEntry["status"], "up" | "warn" | "down" | "neutral"> = {
  sent: "up",
  pending: "warn",
  sending: "warn",
  failed: "down",
  cancelled: "neutral",
};

function DeliveryLogSection() {
  const { data, reload } = useApi<DeliveryLogEntry[]>("/api/account/notifications/log?limit=30", {
    refreshMs: 15_000,
  });
  return (
    <SettingsSection title="Recent alert emails" description="Delivery status of the last 30 alert emails.">
      {!data ? <Skeleton className="h-32" /> : data.length === 0 ? (
        <p className="text-sm text-fg-muted">No alert emails yet. Use “Send test alert” to try it.</p>
      ) : (
        <div className="-mx-6 -my-6 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="border-b border-line text-left text-xs text-fg-subtle">
              <tr>
                <th className="px-6 py-3 font-medium">When</th>
                <th className="px-2 py-3 font-medium">Type</th>
                <th className="px-2 py-3 font-medium">To</th>
                <th className="px-6 py-3 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap px-6 py-2.5 text-fg-muted">{timeAgo(e.created_at)}</td>
                  <td className="px-2 py-2.5">
                    {e.incident_id ? (
                      <Link href={`/incidents/${e.incident_id}`} className="hover:text-accent">{KIND_LABEL[e.kind] ?? e.kind}</Link>
                    ) : (KIND_LABEL[e.kind] ?? e.kind)}
                  </td>
                  <td className="max-w-[220px] truncate px-2 py-2.5 text-fg-muted">{e.recipient}</td>
                  <td className="px-6 py-2.5 text-right" title={e.last_error ?? undefined}>
                    <Badge tone={STATUS_TONE[e.status]}>
                      {e.status === "pending" && e.attempts > 0 ? `retrying (${e.attempts})` : e.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t border-line px-6 py-3 text-right">
            <button type="button" onClick={() => void reload()} className="text-xs text-fg-muted hover:text-fg">
              Refresh
            </button>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}
