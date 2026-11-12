"use client";

import { type FormEvent, useState } from "react";
import { Pencil, Plus } from "lucide-react";
import { Alert, Badge, Button, PageHeader, SelectField, Skeleton, TextField, Toggle } from "@/components/ui";
import { ApiError, api, type FieldErrors } from "@/lib/api";
import type { AdminLicenceProduct, AdminPlan } from "@/lib/admin-types";
import { formatInterval, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const INTERVALS = [30, 60, 120, 300, 600, 900, 1800, 3600];

type PlanForm = Omit<AdminPlan, "id" | "interval" | "subscribers"> & { price: string };

function toForm(p?: AdminPlan): PlanForm {
  return {
    code: p?.code ?? "", name: p?.name ?? "", description: p?.description ?? "",
    price_cents: p?.price_cents ?? 0, price: p ? (p.price_cents / 100).toFixed(2) : "",
    currency: p?.currency ?? "CHF", max_monitors: p?.max_monitors ?? 10,
    min_interval_seconds: p?.min_interval_seconds ?? 60, is_active: p?.is_active ?? true,
    is_public: p?.is_public ?? true, sort_order: p?.sort_order ?? 100,
  };
}

function PlanEditor({ plan, onDone }: { plan?: AdminPlan; onDone: () => void }) {
  const [f, setF] = useState<PlanForm>(() => toForm(plan));
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof PlanForm>(k: K, v: PlanForm[K]) => setF((s) => ({ ...s, [k]: v }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});
    const price = Math.round(Number(f.price.replace(",", ".")) * 100);
    if (!Number.isFinite(price) || price < 0) {
      setFields({ price_cents: "Enter a valid price" });
      setBusy(false);
      return;
    }
    const body = {
      name: f.name, description: f.description, price_cents: price, currency: f.currency,
      max_monitors: f.max_monitors, min_interval_seconds: f.min_interval_seconds,
      is_active: f.is_active, is_public: f.is_public, sort_order: f.sort_order,
    };
    try {
      if (plan) await api(`/api/admin/plans/${plan.code}`, { method: "PUT", body });
      else await api("/api/admin/plans", { method: "POST", body: { ...body, code: f.code } });
      onDone();
    } catch (err) {
      if (err instanceof ApiError) {
        setFields(err.fields);
        if (!Object.keys(err.fields).length) setError(err.message);
      }
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-4 border-t border-line p-5">
      {error && <Alert tone="error">{error}</Alert>}
      {plan && plan.subscribers > 0 && (
        <Alert tone="warning">
          {plan.subscribers} customer(s) use this plan. Limit changes apply to them immediately; a new price applies from their next renewal.
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {!plan && <TextField label="Code" value={f.code} onChange={(e) => set("code", e.target.value.toLowerCase())}
          error={fields.code} hint="e.g. team — used in URLs, cannot change later" />}
        <TextField label="Name" value={f.name} onChange={(e) => set("name", e.target.value)} error={fields.name} />
        <TextField label={`Price per month (${f.currency})`} inputMode="decimal" value={f.price}
          onChange={(e) => set("price", e.target.value)} error={fields.price_cents} />
        <TextField label="Monitors" type="number" min={1} value={f.max_monitors}
          onChange={(e) => set("max_monitors", Number(e.target.value))} error={fields.max_monitors} />
        <SelectField label="Fastest check interval" value={f.min_interval_seconds}
          onChange={(e) => set("min_interval_seconds", Number(e.target.value))} error={fields.min_interval_seconds}>
          {INTERVALS.map((i) => <option key={i} value={i}>{formatInterval(i)}</option>)}
        </SelectField>
        <TextField label="Sort order" type="number" min={0} value={f.sort_order}
          onChange={(e) => set("sort_order", Number(e.target.value))} />
        <TextField className="sm:col-span-2 lg:col-span-3" label="Description" value={f.description} maxLength={500}
          onChange={(e) => set("description", e.target.value)} error={fields.description} />
      </div>
      <div className="grid gap-x-8 sm:grid-cols-2">
        <Toggle label="Available" description="New customers can subscribe." checked={f.is_active} onChange={(v) => set("is_active", v)} />
        <Toggle label="Shown on pricing page" description="Hidden plans can still be assigned." checked={f.is_public} onChange={(v) => set("is_public", v)} />
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
        <Button type="submit" loading={busy}>{plan ? "Save plan" : "Create plan"}</Button>
      </div>
    </form>
  );
}

export function PlansView() {
  const plans = useApi<AdminPlan[]>("/api/admin/plans");
  const products = useApi<AdminLicenceProduct[]>("/api/admin/licence-products");
  const [editing, setEditing] = useState<string | null>(null);

  if (plans.error) return <Alert tone="error">{plans.error.message}</Alert>;
  const done = () => { setEditing(null); void plans.reload(); };

  return (
    <>
      <PageHeader title="Plans & pricing" description="Subscription plans for the hosted service and self-hosted licence prices."
        actions={<Button variant="secondary" onClick={() => setEditing("__new")}><Plus className="h-4 w-4" /> New plan</Button>} />
      {!plans.data ? <Skeleton className="h-64" /> : (
        <div className="space-y-3">
          {editing === "__new" && (
            <div className="card"><p className="px-5 pt-5 font-semibold">New plan</p><PlanEditor onDone={done} /></div>
          )}
          {plans.data.map((p) => (
            <div key={p.code} className="card overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-4 p-5">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 font-semibold">
                    {p.name} <span className="font-mono text-xs text-fg-subtle">{p.code}</span>
                    {!p.is_active && <Badge>Unavailable</Badge>}
                    {!p.is_public && <Badge>Hidden</Badge>}
                  </p>
                  <p className="mt-1 text-sm text-fg-muted">
                    {formatMoney(p.price_cents, p.currency)} / {p.interval} · {p.max_monitors} monitors · every {formatInterval(p.min_interval_seconds)} · {p.subscribers} subscriber(s)
                  </p>
                </div>
                {editing !== p.code && (
                  <Button size="sm" variant="secondary" onClick={() => setEditing(p.code)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>
                )}
              </div>
              {editing === p.code && <PlanEditor plan={p} onDone={done} />}
            </div>
          ))}
        </div>
      )}

      <h2 className="mt-10 text-lg font-semibold">Self-hosted licences</h2>
      <p className="mt-1 text-sm text-fg-muted">One-time prices. Changing limits here affects new licences only — issued licence files never change.</p>
      {!products.data ? <Skeleton className="mt-4 h-40" /> : (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {products.data.map((p) => <LicenceProductCard key={p.code} product={p} onSaved={() => void products.reload()} />)}
        </div>
      )}
    </>
  );
}

function LicenceProductCard({ product, onSaved }: { product: AdminLicenceProduct; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState((product.price_cents / 100).toFixed(2));
  const [limits, setLimits] = useState(product.limits);
  const [active, setActive] = useState(product.is_active);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/api/admin/licence-products/${product.code}`, {
        method: "PUT",
        body: { name: product.name, description: product.description, currency: product.currency,
          sort_order: product.sort_order, price_cents: Math.round(Number(price.replace(",", ".")) * 100),
          limits, is_active: active },
      });
      setOpen(false);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saving failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{product.name} {!product.is_active && <Badge>Unavailable</Badge>}</p>
          <p className="mt-1 text-sm text-fg-muted">
            {formatMoney(product.price_cents, product.currency)} one-time · {product.limits.max_monitors || "∞"} monitors · {product.limits.max_users || "∞"} users · every {formatInterval(product.limits.min_interval_seconds)}
          </p>
        </div>
        {!open && <Button size="sm" variant="secondary" onClick={() => setOpen(true)}><Pencil className="h-3.5 w-3.5" /> Edit</Button>}
      </div>
      {open && (
        <form onSubmit={save} className="mt-4 space-y-3">
          {error && <Alert tone="error">{error}</Alert>}
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label={`Price (${product.currency})`} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
            <TextField label="Monitors (0 = unlimited)" type="number" min={0} value={limits.max_monitors}
              onChange={(e) => setLimits({ ...limits, max_monitors: Number(e.target.value) })} />
            <TextField label="Users (0 = unlimited)" type="number" min={0} value={limits.max_users}
              onChange={(e) => setLimits({ ...limits, max_users: Number(e.target.value) })} />
            <SelectField label="Fastest interval" value={limits.min_interval_seconds}
              onChange={(e) => setLimits({ ...limits, min_interval_seconds: Number(e.target.value) })}>
              {INTERVALS.map((i) => <option key={i} value={i}>{formatInterval(i)}</option>)}
            </SelectField>
          </div>
          <Toggle label="Available for purchase" checked={active} onChange={setActive} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Save</Button>
          </div>
        </form>
      )}
    </div>
  );
}
