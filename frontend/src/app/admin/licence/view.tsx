"use client";

import { type ChangeEvent, useState } from "react";
import { Upload } from "lucide-react";
import { Alert, Badge, Button, ConfirmDialog, PageHeader, Skeleton } from "@/components/ui";
import { ApiError, api, type Limits } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime, formatInterval } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type LicenceStatus = {
  installed: boolean;
  source: "file" | "database" | null;
  error: string | null;
  file_path_configured: boolean;
  licence: {
    license_id: string;
    edition: string;
    licensee_name: string;
    licensee_email: string;
    issued_at: string;
    key_id: string;
    updates: string;
    limits: { max_monitors: number; max_users: number; min_interval_seconds: number };
    development_key: boolean;
  } | null;
  limits: Limits;
  usage: { active_monitors: number; limit_paused_monitors: number; users: number };
  history: { license_id: string; edition: string; licensee_name: string; is_active: boolean; installed_at: string }[];
};

function Meter({ label, used, max }: { label: string; used: number; max: number | null }) {
  const pct = max ? Math.min(100, Math.round((used / max) * 100)) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span className="text-fg-muted">{label}</span>
        <span className="tnum">{used} / {max ?? "∞"}</span>
      </div>
      <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
        <div className={max && pct >= 100 ? "h-full bg-warn" : "h-full bg-up"} style={{ width: max ? `${pct}%` : "4%" }} />
      </div>
    </div>
  );
}

export function LicenceView() {
  const { refresh } = useAuth();
  const { data, error, reload } = useApi<LicenceStatus>("/api/admin/licence");
  const [text, setText] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error" | "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  if (error) return <Alert tone="info">{error.status === 404 ? "Licences only apply to self-hosted installations." : error.message}</Alert>;
  if (!data) return <Skeleton className="h-96" />;
  const lic = data.licence;

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) setText(await file.text());
  }

  async function install() {
    setBusy("install");
    setFieldError(null);
    setMsg(null);
    try {
      const res = await api<{ edition: string; paused: number; resumed: number; file_overrides: boolean }>(
        "/api/admin/licence", { method: "POST", body: { licence_text: text } });
      setText("");
      const notes = [res.resumed ? `${res.resumed} paused monitor(s) resumed.` : "",
        res.file_overrides ? "Note: a licence file configured on the server takes precedence over this one." : ""].filter(Boolean).join(" ");
      setMsg({ tone: res.file_overrides ? "warning" : "success", text: `${res.edition.charAt(0).toUpperCase()}${res.edition.slice(1)} licence installed. ${notes}`.trim() });
      await Promise.all([reload(), refresh()]);
    } catch (err) {
      setFieldError(err instanceof ApiError ? err.message : "Installation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function remove() {
    setBusy("remove");
    try {
      const res = await api<{ paused: number }>("/api/admin/licence", { method: "DELETE" });
      setMsg({ tone: "success", text: `Licence removed — evaluation mode is active.${res.paused ? ` ${res.paused} monitor(s) were paused (not deleted).` : ""}` });
      await Promise.all([reload(), refresh()]);
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Removal failed." });
    } finally {
      setBusy(null);
      setConfirmRemove(false);
    }
  }

  return (
    <>
      <PageHeader title="Licence" description="Your licence is verified on this server only — no activation, no internet connection, no expiry." />
      {msg && <Alert tone={msg.tone} className="mb-6">{msg.text}</Alert>}
      {data.error && <Alert tone="error" title="The configured licence was rejected" className="mb-6">{data.error}</Alert>}

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <section className="card p-6">
          {lic ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                                <h2 className="text-lg font-semibold capitalize">{lic.edition} licence</h2>
                <Badge tone="up">Valid</Badge>
                {lic.development_key && <Badge tone="warn">Development key</Badge>}
              </div>
              <dl className="mt-5 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                <div><dt className="text-fg-subtle">Licensed to</dt><dd className="font-medium">{lic.licensee_name}</dd></div>
                <div><dt className="text-fg-subtle">Contact</dt><dd>{lic.licensee_email}</dd></div>
                <div><dt className="text-fg-subtle">Issued</dt><dd>{formatDateTime(lic.issued_at)}</dd></div>
                <div><dt className="text-fg-subtle">Expires</dt><dd>Never</dd></div>
                <div><dt className="text-fg-subtle">Updates</dt><dd className="capitalize">{lic.updates}</dd></div>
                <div><dt className="text-fg-subtle">Installed from</dt><dd>{data.source === "file" ? "Licence file on the server" : "This dashboard"}</dd></div>
                <div className="sm:col-span-2"><dt className="text-fg-subtle">Licence ID</dt><dd className="break-all font-mono text-xs">{lic.license_id}</dd></div>
              </dl>
              {lic.development_key && (
                <p className="mt-4 text-xs text-warn-ink">Signed with a development key — only accepted while UPTIVORA_ENV is development or test.</p>
              )}
              {data.source === "database" && (
                <Button variant="ghost" size="sm" className="mt-5 px-0" onClick={() => setConfirmRemove(true)}>Remove licence</Button>
              )}
            </>
          ) : (
            <div className="flex gap-4">
              
              <div>
                <h2 className="text-lg font-semibold">Evaluation mode</h2>
                <p className="mt-1 text-sm text-fg-muted">
                  Without a licence this installation monitors up to {data.limits.max_monitors} websites for {data.limits.max_users} user, every {formatInterval(data.limits.min_interval_seconds)} or slower.
                  Install your licence file below to unlock your edition.
                </p>
              </div>
            </div>
          )}
        </section>

        <section className="card space-y-5 p-6">
          <h2 className="font-semibold">Usage</h2>
          <Meter label="Active monitors" used={data.usage.active_monitors} max={data.limits.max_monitors} />
          <Meter label="User accounts" used={data.usage.users} max={data.limits.max_users} />
          <p className="text-sm text-fg-muted">Fastest check interval: {formatInterval(data.limits.min_interval_seconds)}</p>
          {data.usage.limit_paused_monitors > 0 && (
            <Alert tone="warning">{data.usage.limit_paused_monitors} monitor(s) are paused because of the licence limit. They resume automatically when there is room.</Alert>
          )}
        </section>
      </div>

      <section className="card mt-6 p-6">
        <h2 className="font-semibold">{lic ? "Replace licence" : "Install licence"}</h2>
        <p className="mt-1 text-sm text-fg-muted">
          Upload the <code className="rounded bg-muted px-1">.uptivora-license</code> file you received, or paste its contents.
          {data.file_path_configured && " A licence file path is configured on the server; a file at that path takes precedence."}
        </p>
        <div className="mt-4 space-y-3">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-[3px] border border-line-strong bg-hover px-3 py-2 text-sm font-medium hover:bg-muted">
            <Upload className="h-4 w-4" /> Choose licence file
            <input type="file" accept=".uptivora-license,.license,.txt" className="sr-only" onChange={onFile} />
          </label>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={7}
            placeholder="-----BEGIN UPTIVORA LICENSE-----" aria-label="Licence text"
            className={`input font-mono text-[11px] ${fieldError ? "input-error" : ""}`} />
          {fieldError && <p className="text-xs text-down-ink" role="alert">{fieldError}</p>}
          <Button onClick={install} loading={busy === "install"} disabled={text.trim().length < 50}>Verify & install</Button>
        </div>
      </section>

      {data.history.length > 0 && (
        <section className="card mt-6 overflow-hidden">
          <h2 className="border-b border-line px-6 py-4 font-semibold">History</h2>
          <ul className="divide-y divide-line">
            {data.history.map((h) => (
              <li key={h.license_id} className="flex flex-wrap items-center justify-between gap-2 px-6 py-3 text-sm">
                <span><span className="capitalize">{h.edition}</span> · {h.licensee_name} <span className="font-mono text-xs text-fg-subtle">{h.license_id.slice(0, 8)}</span></span>
                <span className="flex items-center gap-2 text-xs text-fg-subtle">
                  {formatDateTime(h.installed_at)} {h.is_active && <Badge tone="up">Active</Badge>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <ConfirmDialog open={confirmRemove} title="Remove the licence?" confirmLabel="Remove licence"
        loading={busy === "remove"} onConfirm={remove} onCancel={() => setConfirmRemove(false)}>
        The installation returns to evaluation limits. Monitors above the limit are paused — nothing is deleted, and re-installing the licence resumes them.
      </ConfirmDialog>
    </>
  );
}
