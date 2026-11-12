"use client";

import { type FormEvent, useState } from "react";
import { Copy, Download, FlaskConical } from "lucide-react";
import { Alert, Button, PageHeader, SelectField, Skeleton, TextField, Toggle } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { AdminPlan } from "@/lib/admin-types";
import { useApi } from "@/lib/use-api";

type DevStatus = { environment: string; dev_key_available: boolean };
type CreatedAccount = { email: string; password: string; plan: string | null; role: string };
type CreatedLicence = { license_id: string; edition: string; licence_text: string; filename: string; limits: Record<string, number> };

export function DevToolsView() {
  const { data: status, error } = useApi<DevStatus>("/api/admin/dev/status");
  if (error) {
    return (
      <>
        <PageHeader title="Dev tools" />
        <Alert tone="info">Development tools are only available when UPTIVORA_ENV is development or test.</Alert>
      </>
    );
  }
  if (!status) return <Skeleton className="h-64" />;
  return (
    <>
      <PageHeader title="Dev tools" description="Create test data quickly. Not available in production." />
      <Alert tone="warning" title={`Environment: ${status.environment}`} className="mb-6">
        Everything created here is test data. Test licences are signed with the local development key and are rejected by production installations.
      </Alert>
      <div className="grid gap-6 lg:grid-cols-2">
        <TestAccount />
        <TestLicence keyAvailable={status.dev_key_available} />
      </div>
    </>
  );
}

function TestAccount() {
  const plans = useApi<AdminPlan[]>("/api/admin/plans");
  const [email, setEmail] = useState("");
  const [plan, setPlan] = useState("pro");
  const [admin, setAdmin] = useState(false);
  const [created, setCreated] = useState<CreatedAccount | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hosted = !plans.error;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCreated(await api<CreatedAccount>("/api/admin/dev/test-account", {
        method: "POST",
        body: { email: email.trim() || null, plan_code: hosted && plan ? plan : null, admin },
      }));
      setEmail("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create account.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 font-semibold"><FlaskConical className="h-4 w-4 text-warn" /> Test account</h2>
      <p className="mt-1 text-sm text-fg-muted">Confirmed email, optional TEST subscription.</p>
      <form onSubmit={submit} className="mt-4 space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <TextField label="Email (optional)" type="email" placeholder="random @example.com address" value={email}
          onChange={(e) => setEmail(e.target.value)} />
        {hosted && plans.data && (
          <SelectField label="Plan" value={plan} onChange={(e) => setPlan(e.target.value)}>
            <option value="">No plan</option>
            {plans.data.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
          </SelectField>
        )}
        <Toggle label="Administrator" checked={admin} onChange={setAdmin} />
        <Button type="submit" loading={busy}>Create test account</Button>
      </form>
      {created && (
        <Alert tone="success" title="Account created" className="mt-4">
          <p className="font-mono text-xs">{created.email}</p>
          <p className="mt-1 font-mono text-xs">Password: {created.password}</p>
          <p className="mt-1 text-xs">Shown once. Plan: {created.plan ?? "none"} · role: {created.role}</p>
        </Alert>
      )}
    </section>
  );
}

function TestLicence({ keyAvailable }: { keyAvailable: boolean }) {
  const [edition, setEdition] = useState("starter");
  const [name, setName] = useState("Test Licensee AG");
  const [maxMonitors, setMaxMonitors] = useState("");
  const [result, setResult] = useState<CreatedLicence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      setResult(await api<CreatedLicence>("/api/admin/dev/test-licence", {
        method: "POST",
        body: { edition, licensee_name: name, max_monitors: maxMonitors === "" ? null : Number(maxMonitors) },
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create licence.");
    } finally {
      setBusy(false);
    }
  }

  function download() {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.licence_text], { type: "text/plain" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: result.filename });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="card p-6">
      <h2 className="flex items-center gap-2 font-semibold"><FlaskConical className="h-4 w-4 text-warn" /> Test licence</h2>
      <p className="mt-1 text-sm text-fg-muted">Signed with the development key in <code>backend/.dev-keys</code>.</p>
      {!keyAvailable && (
        <Alert tone="info" className="mt-4">
          No development key yet. Run <code>python -m licensegen keygen --dev</code> in <code>tools/licensegen</code>.
        </Alert>
      )}
      <form onSubmit={submit} className="mt-4 space-y-4">
        {error && <Alert tone="error">{error}</Alert>}
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectField label="Edition" value={edition} onChange={(e) => setEdition(e.target.value)}>
            <option value="starter">Starter</option>
            <option value="professional">Professional</option>
          </SelectField>
          <TextField label="Max monitors (optional)" type="number" min={0} placeholder="edition default"
            value={maxMonitors} onChange={(e) => setMaxMonitors(e.target.value)} />
        </div>
        <TextField label="Licensee" value={name} onChange={(e) => setName(e.target.value)} />
        <Button type="submit" loading={busy} disabled={!keyAvailable}>Issue test licence</Button>
      </form>
      {result && (
        <div className="mt-4 space-y-2">
          <pre className="max-h-48 overflow-auto rounded-lg border border-line bg-ink-950 p-3 text-[11px] leading-relaxed">{result.licence_text}</pre>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={download}><Download className="h-3.5 w-3.5" /> Download</Button>
            <Button size="sm" variant="ghost" onClick={() => { void navigator.clipboard.writeText(result.licence_text); setCopied(true); }}>
              <Copy className="h-3.5 w-3.5" /> {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
