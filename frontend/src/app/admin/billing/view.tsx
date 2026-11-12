"use client";

import { type ChangeEvent, useState } from "react";
import { Upload } from "lucide-react";
import { Alert, Badge, Button, ConfirmDialog, PageHeader, Skeleton } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { cn, formatDateTime, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Order = {
  id: string;
  status: "pending_payment" | "paid" | "fulfilled" | "refunded" | "cancelled";
  product: string;
  product_code: string;
  edition: string;
  price_cents: number;
  currency: string;
  is_test: boolean;
  licensee_name: string;
  licensee_email: string;
  customer_email: string | null;
  license_id: string | null;
  created_at: string;
  paid_at: string | null;
  fulfilled_at: string | null;
};

type PaymentRow = {
  id: string;
  user_email: string | null;
  amount_cents: number;
  currency: string;
  status: string;
  provider: string;
  is_test: boolean;
  description: string;
  created_at: string;
};

const TABS = [
  { key: "orders", label: "Licence orders" },
  { key: "payments", label: "Payments" },
] as const;
const STATUSES = ["paid", "fulfilled", "refunded", "cancelled", "all"] as const;

export function AdminBillingView() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("orders");
  return (
    <>
      <PageHeader title="Billing & licences" description="Self-hosted licence orders waiting for a signed licence, and all payments." />
      <div className="mb-4 inline-flex rounded-lg border border-line bg-ink-900 p-0.5" role="tablist">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={cn("rounded-md px-3 py-1.5 text-sm font-medium", tab === t.key ? "bg-ink-700 text-fg" : "text-fg-muted hover:text-fg")}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "orders" ? <Orders /> : <Payments />}
    </>
  );
}

function Orders() {
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("paid");
  const { data, error, reload } = useApi<Order[]>(`/api/admin/licence-orders?status=${status}`);
  const [fulfilling, setFulfilling] = useState<Order | null>(null);
  const [text, setText] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) setText(await file.text());
  }

  async function fulfil() {
    if (!fulfilling) return;
    setBusy("fulfil");
    setFieldError(null);
    try {
      await api(`/api/admin/licence-orders/${fulfilling.id}/fulfil`, { method: "POST", body: { licence_text: text } });
      setMsg({ tone: "success", text: `Licence attached. ${fulfilling.customer_email ?? "The customer"} was emailed.` });
      setFulfilling(null);
      setText("");
      await reload();
    } catch (err) {
      setFieldError(err instanceof ApiError ? err.message : "Could not attach the licence.");
    } finally {
      setBusy(null);
    }
  }

  async function refund(o: Order) {
    setBusy(o.id);
    try {
      await api(`/api/admin/licence-orders/${o.id}/refund`, { method: "POST" });
      setMsg({ tone: "success", text: "Order refunded." });
      await reload();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Refund failed." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {STATUSES.map((s) => (
          <button key={s} type="button" onClick={() => setStatus(s)}
            className={cn("rounded-md border px-2.5 py-1 text-xs font-medium capitalize",
              status === s ? "border-line-strong bg-ink-700 text-fg" : "border-line text-fg-muted hover:text-fg")}>
            {s === "paid" ? "waiting for licence" : s}
          </button>
        ))}
      </div>
      {msg && <Alert tone={msg.tone} className="mb-4">{msg.text}</Alert>}
      {error && <Alert tone="error">{error.message}</Alert>}
      {!data && !error && <Skeleton className="h-64" />}
      {data && data.length === 0 && <p className="card p-6 text-sm text-fg-muted">No orders.</p>}
      {data && data.length > 0 && (
        <ul className="card divide-y divide-line">
          {data.map((o) => (
            <li key={o.id} className="flex flex-col gap-3 px-5 py-4 text-sm lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 font-medium">
                  {o.product} <Badge>{o.edition}</Badge> {o.is_test && <Badge tone="warn">Test</Badge>}
                </p>
                <p className="mt-0.5 text-fg-muted">Licensee: {o.licensee_name} &lt;{o.licensee_email}&gt;</p>
                <p className="text-xs text-fg-subtle">
                  {o.customer_email ?? "deleted user"} · {formatMoney(o.price_cents, o.currency)} · ordered {formatDateTime(o.created_at)}
                  {o.license_id && <> · licence {o.license_id.slice(0, 8)}</>}
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Badge tone={o.status === "fulfilled" ? "up" : o.status === "paid" ? "warn" : "neutral"}>{o.status}</Badge>
                {o.status === "paid" && (
                  <Button size="sm" onClick={() => { setFulfilling(o); setText(""); setFieldError(null); }}>
                    <Upload className="h-3.5 w-3.5" /> Attach licence
                  </Button>
                )}
                {(o.status === "paid" || o.status === "fulfilled") && o.is_test && (
                  <Button size="sm" variant="ghost" loading={busy === o.id} onClick={() => refund(o)}>Refund</Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog open={fulfilling !== null} tone="primary" title="Attach signed licence"
        confirmLabel="Verify & attach" loading={busy === "fulfil"} onConfirm={fulfil}
        onCancel={() => setFulfilling(null)}>
        {fulfilling && (
          <div className="space-y-3">
            <p>Sign the licence on your offline machine, then upload or paste the file:</p>
            <pre className="overflow-x-auto rounded-lg border border-line bg-ink-950 p-3 text-[11px] text-fg">
{`python -m licensegen issue --key <your key>.pem --key-id <id> \\
  --edition ${fulfilling.edition} --name "${fulfilling.licensee_name}" \\
  --email ${fulfilling.licensee_email} --order ${fulfilling.id} --out order.uptivora-license`}
            </pre>
            <input type="file" accept=".uptivora-license,.license,.txt" onChange={onFile}
              className="block w-full text-xs text-fg-muted file:mr-3 file:rounded-md file:border-0 file:bg-ink-700 file:px-3 file:py-1.5 file:text-fg" />
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6}
              placeholder="-----BEGIN UPTIVORA LICENSE-----" className="input font-mono text-[11px]" />
            {fieldError && <p className="text-xs text-[#fda4af]" role="alert">{fieldError}</p>}
            <p className="text-xs text-fg-subtle">The server checks the signature with the built-in public keys and that the edition matches the order before accepting it.</p>
          </div>
        )}
      </ConfirmDialog>
    </>
  );
}

function Payments() {
  const { data, error } = useApi<PaymentRow[]>("/api/admin/payments?limit=200");
  if (error) return <Alert tone="error">{error.message}</Alert>;
  if (!data) return <Skeleton className="h-64" />;
  if (data.length === 0) return <p className="card p-6 text-sm text-fg-muted">No payments yet.</p>;
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[680px] text-sm">
        <thead className="border-b border-line text-left text-xs text-fg-subtle">
          <tr><th className="px-5 py-3 font-medium">Date</th><th className="px-2 py-3 font-medium">Customer</th><th className="px-2 py-3 font-medium">Description</th><th className="px-2 py-3 text-right font-medium">Amount</th><th className="px-5 py-3 text-right font-medium">Status</th></tr>
        </thead>
        <tbody className="divide-y divide-line">
          {data.map((p) => (
            <tr key={p.id}>
              <td className="whitespace-nowrap px-5 py-2.5 text-fg-muted">{formatDateTime(p.created_at)}</td>
              <td className="max-w-[200px] truncate px-2 py-2.5">{p.user_email ?? "—"}</td>
              <td className="px-2 py-2.5">{p.description} {p.is_test && <Badge tone="warn">Test</Badge>}</td>
              <td className="tnum whitespace-nowrap px-2 py-2.5 text-right">{formatMoney(p.amount_cents, p.currency)}</td>
              <td className="px-5 py-2.5 text-right"><Badge tone={p.status === "succeeded" ? "up" : p.status === "failed" ? "down" : "neutral"}>{p.status}</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
