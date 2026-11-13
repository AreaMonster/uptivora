"use client";

import { type FormEvent, useState } from "react";
import { RotateCw, Trash2 } from "lucide-react";
import { Alert, Badge, Button, SelectField, TextField } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Invitation = { id: string; email: string; role: "user" | "admin"; invited_at: string };

/** Self-hosted only: renders nothing on hosted installations (the endpoint returns 404). */
export function Invitations({ onChanged }: { onChanged?: () => void }) {
  const { data, error, reload } = useApi<Invitation[]>("/api/admin/invitations");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (error?.status === 404) return null;
  if (error) return <Alert tone="error" className="mb-6">{error.message}</Alert>;

  async function invite(e: FormEvent) {
    e.preventDefault();
    setBusy("invite");
    setFieldError(undefined);
    setMsg(null);
    try {
      await api("/api/admin/invitations", { method: "POST", body: { email, role } });
      setMsg({ tone: "success", text: `Invitation sent to ${email}. The link is valid for 7 days.` });
      setEmail("");
      await reload();
      onChanged?.();
    } catch (err) {
      if (err instanceof ApiError && err.fields.email) setFieldError(err.fields.email);
      else setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Could not send invitation." });
    } finally {
      setBusy(null);
    }
  }

  async function act(key: string, fn: () => Promise<unknown>, text: string) {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
      setMsg({ tone: "success", text });
      await reload();
      onChanged?.();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Request failed." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="card mb-6 p-5">
      <h2 className="font-semibold">Invite a colleague</h2>
      <p className="mt-1 text-sm text-fg-muted">They receive an email to choose a password. Invited accounts count towards your licence’s user limit.</p>
      {msg && <Alert tone={msg.tone} className="mt-4">{msg.text}</Alert>}
      <form onSubmit={invite} className="mt-4 grid gap-3 sm:grid-cols-[1fr_160px_auto] sm:items-start">
        <TextField label="Email" type="email" required value={email} error={fieldError}
          onChange={(e) => setEmail(e.target.value)} placeholder="colleague@example.com" />
        <SelectField label="Role" value={role} onChange={(e) => setRole(e.target.value as "user" | "admin")}>
          <option value="user">User</option>
          <option value="admin">Administrator</option>
        </SelectField>
        <Button type="submit" className="sm:mt-[26px]" loading={busy === "invite"} disabled={!email}>Send invitation</Button>
      </form>
      {data && data.length > 0 && (
        <ul className="mt-5 divide-y divide-line rounded-[3px] border border-line">
          {data.map((inv) => (
            <li key={inv.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium">{inv.email}</p>
                <p className="text-xs text-fg-subtle">Invited {timeAgo(inv.invited_at)}</p>
              </div>
              <div className="flex items-center gap-1">
                <Badge tone="warn">Pending</Badge>
                {inv.role === "admin" && <Badge>Admin</Badge>}
                <Button size="sm" variant="ghost" loading={busy === `resend-${inv.id}`}
                  onClick={() => act(`resend-${inv.id}`, () => api(`/api/admin/invitations/${inv.id}/resend`, { method: "POST" }), `Invitation sent again to ${inv.email}.`)}>
                  <RotateCw className="h-3.5 w-3.5" /> Resend
                </Button>
                <Button size="sm" variant="ghost" aria-label={`Revoke invitation for ${inv.email}`} loading={busy === `revoke-${inv.id}`}
                  onClick={() => act(`revoke-${inv.id}`, () => api(`/api/admin/invitations/${inv.id}`, { method: "DELETE" }), "Invitation revoked.")}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Step = { key: string; label: string; done: boolean };

/** Self-hosted only: first-run checklist on the admin overview. */
export function SetupChecklist() {
  const { data, error } = useApi<{ steps: Step[] }>("/api/admin/setup", { refreshMs: 30_000 });
  if (error || !data) return null;
  const remaining = data.steps.filter((s) => !s.done).length;
  if (remaining === 0) return null;
  return (
    <section className="card mb-6 p-5">
      <h2 className="font-semibold">Finish setting up your installation</h2>
      <p className="mt-1 text-sm text-fg-muted">{remaining} step(s) left. See the self-hosting guide for details.</p>
      <ol className="mt-4 space-y-2">
        {data.steps.map((s) => (
          <li key={s.key} className="flex items-center gap-3 text-sm">
            <span className={s.done ? "grid h-5 w-5 place-items-center rounded-full bg-up text-[11px] font-bold text-canvas" : "h-5 w-5 rounded-full border border-line-strong"}>
              {s.done ? "✓" : ""}
            </span>
            <span className={s.done ? "text-fg-subtle line-through" : ""}>{s.label}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
