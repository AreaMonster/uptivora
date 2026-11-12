"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useMemo, useState } from "react";
import { Monitor as MonitorIcon, Smartphone } from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  ConfirmDialog,
  PageHeader,
  SelectField,
  Skeleton,
  TextField,
} from "@/components/ui";
import { ApiError, api, type FieldErrors, type Me } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatInterval, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { NotificationSettings } from "@/components/app/notification-settings";
import { SettingsSection } from "@/components/app/settings-section";

export function SettingsPage() {
  const { me } = useAuth();
  if (!me) return null;
  return (
    <>
      <PageHeader title="Settings" description="Your profile, alerts and account security." />
      <ProfileSection />
      <PlanSection />
      <NotificationSettings />
      <PasswordSection />
      <SessionsSection />
      <DangerSection />
    </>
  );
}

function ProfileSection() {
  const { me, setMe } = useAuth();
  const [name, setName] = useState(me?.user.full_name ?? "");
  const [tz, setTz] = useState(me?.user.timezone ?? "UTC");
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const zones = useMemo(() => {
    try {
      return Intl.supportedValuesOf("timeZone");
    } catch {
      return ["UTC", "Europe/Zurich"];
    }
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      setMe(await api<Me>("/api/account", { method: "PATCH", body: { full_name: name, timezone: tz } }));
      setMsg({ tone: "success", text: "Profile saved." });
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Saving failed." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <SettingsSection title="Profile" description="Times in the dashboard are shown in your time zone.">
      <form onSubmit={save} className="space-y-4">
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
        <TextField label="Email" value={me?.user.email ?? ""} disabled
          hint={me?.user.email_verified ? "Confirmed" : "Not confirmed yet"} />
        <TextField label="Full name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        <SelectField label="Time zone" value={tz} onChange={(e) => setTz(e.target.value)}>
          {[...new Set(["UTC", ...zones])].map((z) => <option key={z} value={z}>{z}</option>)}
        </SelectField>
        <div className="flex justify-end"><Button type="submit" loading={busy}>Save profile</Button></div>
      </form>
    </SettingsSection>
  );
}

function PlanSection() {
  const { me } = useAuth();
  if (!me) return null;
  const { limits, usage } = me;
  const sourceLabel = {
    plan: `${limits.plan_name} plan`,
    no_plan: "No active plan",
    admin: "Administrator (no limits)",
    licence: `${limits.edition} licence — ${limits.licensee}`,
    unlicensed: "Evaluation mode (no licence)",
  }[limits.source];
  return (
    <SettingsSection title={limits.scope === "instance" ? "Licence" : "Plan"}
      description={limits.scope === "instance" ? "Limits apply to this whole installation." : "Your current plan and usage."}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-medium capitalize">{sourceLabel}</p>
        {limits.source === "no_plan" && <Badge tone="warn">Action needed</Badge>}
      </div>
      <dl className="mt-5 grid gap-4 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-fg-subtle">Active monitors</dt>
          <dd className="tnum mt-1 text-lg font-semibold">
            {usage.active_monitors}{limits.max_monitors != null && <span className="text-fg-muted"> / {limits.max_monitors}</span>}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-fg-subtle">Fastest check interval</dt>
          <dd className="mt-1 text-lg font-semibold">{formatInterval(limits.min_interval_seconds)}</dd>
        </div>
        {limits.scope === "instance" && (
          <div>
            <dt className="text-xs text-fg-subtle">User accounts</dt>
            <dd className="mt-1 text-lg font-semibold">{limits.max_users ?? "Unlimited"}</dd>
          </div>
        )}
      </dl>
      {limits.scope === "user" && (
        <p className="mt-5 text-sm text-fg-muted">
          Online upgrades, downgrades and billing history are coming to this page soon.
        </p>
      )}
    </SettingsSection>
  );
}

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [fields, setFields] = useState<FieldErrors>({});
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    setFields({});
    try {
      await api("/api/account/password", { method: "POST", body: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      setMsg({ tone: "success", text: "Password changed. Your other sessions were signed out." });
    } catch (err) {
      if (err instanceof ApiError) {
        setFields({ ...err.fields, new_password: err.fields.password ?? err.fields.new_password });
        if (!Object.keys(err.fields).length) setMsg({ tone: "error", text: err.message });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <SettingsSection title="Password" description="Changing it signs you out everywhere else.">
      <form onSubmit={save} className="space-y-4">
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
        <TextField label="Current password" type="password" autoComplete="current-password"
          value={current} onChange={(e) => setCurrent(e.target.value)} error={fields.current_password} />
        <TextField label="New password" type="password" autoComplete="new-password" minLength={10}
          value={next} onChange={(e) => setNext(e.target.value)} error={fields.new_password}
          hint="At least 10 characters." />
        <div className="flex justify-end">
          <Button type="submit" loading={busy} disabled={!current || !next}>Change password</Button>
        </div>
      </form>
    </SettingsSection>
  );
}

type SessionRow = { id: string; created_at: string; last_seen_at: string; ip_address: string | null; user_agent: string | null; current: boolean };

function describeAgent(ua: string | null): string {
  if (!ua) return "Unknown device";
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${browser} on ${os}` : browser;
}

function SessionsSection() {
  const { data, reload } = useApi<SessionRow[]>("/api/account/sessions");
  const [busyId, setBusyId] = useState<string | null>(null);

  async function revoke(id: string) {
    setBusyId(id);
    try {
      await api(`/api/account/sessions/${id}`, { method: "DELETE" });
      await reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <SettingsSection title="Active sessions" description="Devices currently signed in to your account.">
      {!data ? <Skeleton className="h-24" /> : (
        <ul className="divide-y divide-line">
          {data.map((s) => {
            const mobile = /Mobile|Android|iPhone/.test(s.user_agent ?? "");
            const Icon = mobile ? Smartphone : MonitorIcon;
            return (
              <li key={s.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div className="flex min-w-0 items-center gap-3">
                  <Icon className="h-5 w-5 shrink-0 text-fg-subtle" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {describeAgent(s.user_agent)} {s.current && <Badge tone="up">This device</Badge>}
                    </p>
                    <p className="truncate text-xs text-fg-subtle">
                      {s.ip_address ?? "unknown IP"} · active {timeAgo(s.last_seen_at)}
                    </p>
                  </div>
                </div>
                {!s.current && (
                  <Button size="sm" variant="ghost" loading={busyId === s.id} onClick={() => revoke(s.id)}>
                    Sign out
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </SettingsSection>
  );
}

function DangerSection() {
  const router = useRouter();
  const { setMe } = useAuth();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function close() {
    setOpen(false);
    setPassword("");
    setError(null);
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/account", { method: "DELETE", body: { password } });
      setMe(null);
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Deletion failed.");
      setBusy(false);
    }
  }

  return (
    <SettingsSection title="Delete account" description="Permanently remove your account, monitors and history.">
      <p className="text-sm text-fg-muted">
        This deletes all your monitors, check results and incidents immediately. It cannot be undone.
      </p>
      <Button variant="danger" className="mt-4" onClick={() => setOpen(true)}>Delete my account</Button>
      <ConfirmDialog open={open} title="Delete your account?" confirmLabel="Delete permanently"
        loading={busy} onConfirm={remove} onCancel={close}>
        <p>Enter your password to confirm. All data is removed permanently.</p>
        <div className="mt-4">
          <TextField label="Password" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} error={error ?? undefined} />
        </div>
      </ConfirmDialog>
    </SettingsSection>
  );
}
