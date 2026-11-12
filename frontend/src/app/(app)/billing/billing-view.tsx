"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Check, CreditCard, Download, FlaskConical, KeyRound } from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  ConfirmDialog,
  PageHeader,
  Skeleton,
  TextField,
  Toggle,
} from "@/components/ui";
import { ApiError, api, type BillingPlan, type BillingQuote, type BillingSummary, type LicenceProduct } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn, formatDateTime, formatInterval, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Simulate = "success" | "decline";
type Msg = { tone: "success" | "error" | "info"; text: string } | null;

function TestCardPicker({ value, onChange }: { value: Simulate; onChange: (v: Simulate) => void }) {
  return (
    <fieldset className="mt-4 rounded-xl border border-warn/30 bg-warn-soft p-3">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-[#fde68a]">Test card</legend>
      {(["success", "decline"] as const).map((v) => (
        <label key={v} className="flex cursor-pointer items-center gap-2.5 py-1 text-sm text-fg">
          <input type="radio" name="simulate" checked={value === v} onChange={() => onChange(v)}
            className="accent-[#f59e0b]" />
          {v === "success" ? "Card that pays successfully" : "Card that is declined"}
        </label>
      ))}
      <p className="mt-1 text-xs text-[#fde68a]/80">Simulated payment — no real card, no real charge.</p>
    </fieldset>
  );
}

export function BillingView() {
  const { refresh } = useAuth();
  const params = useSearchParams();
  const { data, error, reload } = useApi<BillingSummary>("/api/billing");
  const [msg, setMsg] = useState<Msg>(null);
  const [checkout, setCheckout] = useState<{ plan: BillingPlan; quote: BillingQuote | null } | null>(null);
  const [simulate, setSimulate] = useState<Simulate>("success");
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const autoOpened = useRef(false);

  async function openCheckout(plan: BillingPlan) {
    setCheckout({ plan, quote: null });
    setSimulate("success");
    try {
      const quote = await api<BillingQuote>(`/api/billing/quote?plan=${encodeURIComponent(plan.code)}`);
      setCheckout({ plan, quote });
    } catch (err) {
      setCheckout(null);
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Could not prepare checkout." });
    }
  }

  useEffect(() => {
    const code = params.get("plan");
    if (!data || !code || autoOpened.current) return;
    autoOpened.current = true;
    const plan = data.plans.find((p) => p.code === code);
    if (!plan || data.subscription?.plan.code === code) return;
    // Opened from the pricing page (?plan=…): start checkout once the page is shown.
    const id = setTimeout(() => void openCheckout(plan), 0);
    return () => clearTimeout(id);
  }, [data, params]);

  async function run(key: string, fn: () => Promise<unknown>, success: string) {
    setBusy(key);
    setMsg(null);
    try {
      await fn();
      setMsg({ tone: "success", text: success });
      await Promise.all([reload(), refresh()]);
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Request failed." });
      await reload();
    } finally {
      setBusy(null);
    }
  }

  async function confirmCheckout() {
    if (!checkout?.quote) return;
    const { plan, quote } = checkout;
    await run("checkout", () => api("/api/billing/subscribe", { method: "POST", body: { plan_code: plan.code, simulate } }),
      quote.action === "downgrade"
        ? `Your plan changes to ${plan.name} on ${formatDateTime(quote.effective_at)}.`
        : `You are now on the ${plan.name} plan.`);
    setCheckout(null);
  }

  if (error) {
    return (
      <>
        <PageHeader title="Billing" />
        <Alert tone="info">{error.status === 404 ? "Billing is not available on this installation." : error.message}</Alert>
      </>
    );
  }
  if (!data) return <Skeleton className="h-96" />;
  const sub = data.subscription;

  function planAction(p: BillingPlan): { label: string; variant: "primary" | "secondary"; disabled?: boolean } {
    if (!sub) return { label: `Choose ${p.name}`, variant: "primary" };
    if (sub.plan.code === p.code) return { label: "Current plan", variant: "secondary", disabled: true };
    if (sub.pending_plan?.code === p.code) return { label: "Scheduled", variant: "secondary", disabled: true };
    return p.price_cents > sub.plan.price_cents
      ? { label: `Upgrade to ${p.name}`, variant: "primary" }
      : { label: `Downgrade to ${p.name}`, variant: "secondary" };
  }

  return (
    <>
      <PageHeader title="Billing" description="Your plan, payments and self-hosted licences."
        actions={data.test_mode ? <Badge tone="warn">Test mode</Badge> : undefined} />

      {data.test_mode && (
        <Alert tone="warning" title="Payments are in TEST MODE" className="mb-6">
          Online payments are not live yet. Checkout uses a simulated test card: nothing is charged and no card details are asked for.
        </Alert>
      )}
      {!data.enabled && (
        <Alert tone="info" className="mb-6">Online payments are not enabled. Contact us to activate a plan.</Alert>
      )}
      {msg && <Alert tone={msg.tone} className="mb-6">{msg.text}</Alert>}

      {sub?.status === "past_due" && (
        <Alert tone="error" title="Your last payment failed" className="mb-6"
          action={<Button size="sm" variant="secondary" loading={busy === "retry"}
            onClick={() => run("retry", () => api("/api/billing/retry", { method: "POST", body: { simulate } }), "Payment successful — thank you.")}>
            Retry payment
          </Button>}>
          Monitoring continues until {formatDateTime(sub.grace_until)}. We retry automatically every day.
          {data.test_mode && (
            <span className="mt-2 flex gap-4 text-xs">
              {(["success", "decline"] as const).map((v) => (
                <label key={v} className="flex items-center gap-1.5"><input type="radio" checked={simulate === v} onChange={() => setSimulate(v)} /> {v === "success" ? "test card pays" : "test card declined"}</label>
              ))}
            </span>
          )}
        </Alert>
      )}

      {/* Current subscription */}
      <section className="card p-6">
        {sub ? (
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="flex flex-wrap items-center gap-2 text-lg font-semibold">
                {sub.plan.name} plan
                {sub.status === "active" && <Badge tone="up">Active</Badge>}
                {sub.status === "cancelled" && <Badge tone="warn">Cancelled</Badge>}
                {sub.status === "past_due" && <Badge tone="down">Past due</Badge>}
                {sub.is_test && <Badge tone="warn">Test</Badge>}
                {sub.provider === "manual" && <Badge>Assigned by Uptivora</Badge>}
              </p>
              <p className="mt-1 text-sm text-fg-muted">
                {formatMoney(sub.plan.price_cents, sub.plan.currency)} / month · {sub.plan.max_monitors} monitors ({data.usage.active_monitors} active) · checks every {formatInterval(sub.plan.min_interval_seconds)}
              </p>
              <p className="mt-1 text-sm text-fg-muted">
                {sub.cancel_at_period_end ? "Ends" : "Renews"} on {formatDateTime(sub.current_period_end)}
              </p>
              {sub.pending_plan && (
                <p className="mt-3 text-sm text-[#99f6e4]">
                  Changes to {sub.pending_plan.name} on {formatDateTime(sub.current_period_end)}.{" "}
                  <button className="underline" onClick={() => run("keep", () => api("/api/billing/cancel-change", { method: "POST" }), `You stay on ${sub.plan.name}.`)}>
                    Keep {sub.plan.name}
                  </button>
                </p>
              )}
            </div>
            {sub.provider !== "manual" && (
              <div className="flex flex-col gap-3 lg:items-end">
                {sub.status === "cancelled" ? (
                  <Button loading={busy === "resume"} onClick={() => run("resume", () => api("/api/billing/resume", { method: "POST" }), "Your subscription continues.")}>
                    Resume subscription
                  </Button>
                ) : (
                  <Button variant="ghost" onClick={() => setConfirmCancel(true)}>Cancel subscription</Button>
                )}
                {data.test_mode && sub.status !== "cancelled" && (
                  <div className="w-full max-w-xs rounded-lg border border-warn/30 bg-warn-soft px-3">
                    <Toggle label="Test: fail next renewal" checked={sub.simulate_failure}
                      onChange={(v) => run("sim", () => api("/api/billing/test-settings", { method: "PUT", body: { simulate_renewal_failure: v } }),
                        v ? "The next renewal will be declined (test)." : "The next renewal will succeed (test).")} />
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-ink-700 text-accent ring-1 ring-line-strong"><CreditCard className="h-5 w-5" /></div>
            <div>
              <p className="font-semibold">No active plan</p>
              <p className="text-sm text-fg-muted">Choose a plan below to start monitoring. Cancel any time.</p>
            </div>
          </div>
        )}
      </section>

      {/* Plans */}
      <h2 className="mt-10 text-lg font-semibold">Plans</h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {data.plans.map((p) => {
          const action = planAction(p);
          const current = sub?.plan.code === p.code;
          return (
            <div key={p.code} className={cn("card flex flex-col p-6", current && "border-up/50 ring-1 ring-up/30")}>
              <p className="font-semibold">{p.name}</p>
              <p className="mt-1 min-h-10 text-sm text-fg-muted">{p.description}</p>
              <p className="mt-4"><span className="tnum text-3xl font-semibold">{formatMoney(p.price_cents, p.currency)}</span> <span className="text-sm text-fg-muted">/ month</span></p>
              <ul className="mt-4 flex-1 space-y-2 text-sm">
                <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 text-up" />{p.max_monitors} monitors</li>
                <li className="flex gap-2"><Check className="mt-0.5 h-4 w-4 text-up" />Checks every {formatInterval(p.min_interval_seconds)}</li>
              </ul>
              <Button className="mt-6" variant={action.variant} disabled={action.disabled || !data.enabled || sub?.status === "past_due"}
                onClick={() => openCheckout(p)}>
                {action.label}
              </Button>
            </div>
          );
        })}
      </div>

      {/* Payments */}
      <h2 className="mt-10 text-lg font-semibold">Payment history</h2>
      <div className="card mt-4 overflow-x-auto">
        {data.payments.length === 0 ? <p className="p-6 text-sm text-fg-muted">No payments yet.</p> : (
          <table className="w-full min-w-[560px] text-sm">
            <thead className="border-b border-line text-left text-xs text-fg-subtle">
              <tr><th className="px-5 py-3 font-medium">Date</th><th className="px-2 py-3 font-medium">Description</th><th className="px-2 py-3 text-right font-medium">Amount</th><th className="px-5 py-3 text-right font-medium">Status</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.payments.map((p) => (
                <tr key={p.id}>
                  <td className="whitespace-nowrap px-5 py-2.5 text-fg-muted">{formatDateTime(p.created_at)}</td>
                  <td className="px-2 py-2.5">{p.description} {p.is_test && <Badge tone="warn">Test</Badge>}</td>
                  <td className="tnum px-2 py-2.5 text-right">{formatMoney(p.amount_cents, p.currency)}</td>
                  <td className="px-5 py-2.5 text-right">
                    <Badge tone={p.status === "succeeded" ? "up" : p.status === "failed" ? "down" : "neutral"}>{p.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <LicenceStore data={data} testMode={data.test_mode} onChanged={reload} />

      {/* Checkout dialog */}
      <ConfirmDialog open={checkout !== null} tone="primary" loading={busy === "checkout"}
        title={checkout?.quote?.action === "downgrade" ? `Switch to ${checkout.plan.name}` : `Checkout — ${checkout?.plan.name ?? ""}`}
        confirmLabel={!checkout?.quote ? "…" : checkout.quote.action === "downgrade" ? "Schedule change"
          : `Pay ${formatMoney(checkout.quote.amount_cents, checkout.quote.currency)}${data.test_mode ? " (test)" : ""}`}
        onConfirm={confirmCheckout} onCancel={() => setCheckout(null)}>
        {!checkout?.quote ? <Skeleton className="h-24" /> : (
          <div className="space-y-2">
            {checkout.quote.action === "subscribe" && (
              <p>{formatMoney(checkout.quote.amount_cents, checkout.quote.currency)} today, then every month. Cancel any time.</p>
            )}
            {checkout.quote.action === "upgrade" && (
              <p>
                Upgrade from {checkout.quote.current_plan?.name} takes effect immediately. You pay{" "}
                <strong className="text-fg">{formatMoney(checkout.quote.amount_cents, checkout.quote.currency)}</strong> now for the rest of this billing period,
                then {formatMoney(checkout.plan.price_cents, checkout.plan.currency)} per month.
              </p>
            )}
            {checkout.quote.action === "downgrade" && (
              <p>
                You keep {checkout.quote.current_plan?.name} until {formatDateTime(checkout.quote.effective_at)}, then pay {formatMoney(checkout.plan.price_cents, checkout.plan.currency)} per month.
                {checkout.plan.max_monitors < data.usage.active_monitors && (
                  <> Monitors above the new limit of {checkout.plan.max_monitors} will be paused (not deleted).</>
                )}
              </p>
            )}
            {data.test_mode && checkout.quote.action !== "downgrade" && <TestCardPicker value={simulate} onChange={setSimulate} />}
          </div>
        )}
      </ConfirmDialog>

      <ConfirmDialog open={confirmCancel} title="Cancel your subscription?" confirmLabel="Cancel subscription"
        loading={busy === "cancel"} onCancel={() => setConfirmCancel(false)}
        onConfirm={async () => {
          await run("cancel", () => api("/api/billing/cancel", { method: "POST" }),
            sub ? `Cancelled. Monitoring continues until ${formatDateTime(sub.current_period_end)}.` : "Cancelled.");
          setConfirmCancel(false);
        }}>
        {sub && <>Monitoring continues until {formatDateTime(sub.current_period_end)}. After that your monitors are paused — your data is kept and you can resume any time.</>}
      </ConfirmDialog>
    </>
  );
}

const ORDER_STATUS: Record<string, { label: string; tone: "up" | "warn" | "down" | "neutral" }> = {
  paid: { label: "Paid — preparing your licence", tone: "warn" },
  fulfilled: { label: "Ready", tone: "up" },
  refunded: { label: "Refunded", tone: "neutral" },
  cancelled: { label: "Payment failed", tone: "down" },
  pending_payment: { label: "Awaiting payment", tone: "neutral" },
};

function LicenceStore({ data, testMode, onChanged }: { data: BillingSummary; testMode: boolean; onChanged: () => Promise<void> }) {
  const { me } = useAuth();
  const [product, setProduct] = useState<LicenceProduct | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState(me?.user.email ?? "");
  const [simulate, setSimulate] = useState<Simulate>("success");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);

  async function buy() {
    if (!product) return;
    setBusy(true);
    setMsg(null);
    try {
      await api("/api/billing/licence-orders", { method: "POST", body: { product_code: product.code, licensee_name: name, licensee_email: email, simulate } });
      setMsg({ tone: "success", text: "Thank you! Your licence file is being prepared — we’ll email you when it is ready to download." });
      setProduct(null);
      await onChanged();
    } catch (err) {
      setMsg({ tone: "error", text: err instanceof ApiError ? err.message : "Purchase failed." });
      setProduct(null);
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="licences" className="scroll-mt-20">
      <h2 className="mt-10 flex items-center gap-2 text-lg font-semibold"><KeyRound className="h-5 w-5 text-accent" /> Self-hosted licences</h2>
      <p className="mt-1 text-sm text-fg-muted">
        Run Uptivora on your own server with a one-time, lifetime licence. <a href="/self-hosted" className="text-accent hover:underline">What’s included</a>
      </p>
      {msg && <Alert tone={msg.tone} className="mt-4">{msg.text}</Alert>}
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {data.licence_products.map((p) => (
          <div key={p.code} className="card flex flex-col p-6">
            <p className="font-semibold">{p.name}</p>
            <p className="mt-1 text-sm text-fg-muted">{p.description}</p>
            <p className="mt-4"><span className="tnum text-2xl font-semibold">{formatMoney(p.price_cents, p.currency)}</span> <span className="text-sm text-fg-muted">one-time</span></p>
            <Button variant="secondary" className="mt-5" disabled={!data.enabled}
              onClick={() => { setProduct(p); setName(""); setSimulate("success"); }}>
              Buy licence
            </Button>
          </div>
        ))}
      </div>
      {data.licence_orders.length > 0 && (
        <ul className="card mt-4 divide-y divide-line">
          {data.licence_orders.map((o) => {
            const st = ORDER_STATUS[o.status] ?? { label: o.status, tone: "neutral" as const };
            return (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 text-sm">
                <div>
                  <p className="font-medium">{o.product} {o.is_test && <Badge tone="warn">Test</Badge>}</p>
                  <p className="text-xs text-fg-subtle">Licensed to {o.licensee_name} · ordered {formatDateTime(o.created_at)}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge tone={st.tone}>{st.label}</Badge>
                  {o.status === "fulfilled" && (
                    <a href={`/api/billing/licence-orders/${o.id}/download`} download
                      className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-ink-750 px-3 py-1.5 text-xs font-semibold hover:bg-ink-700">
                      <Download className="h-3.5 w-3.5" /> Download
                    </a>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-xs text-fg-subtle">
        Licence files are signed offline and checked by your installation without contacting us. <ButtonLink href="/docs/licensing" variant="ghost" size="sm" className="h-auto px-0 text-xs">How licences work</ButtonLink>
      </p>

      <ConfirmDialog open={product !== null} tone="primary" loading={busy}
        title={`Buy ${product?.name ?? ""}`}
        confirmLabel={product ? `Pay ${formatMoney(product.price_cents, product.currency)}${testMode ? " (test)" : ""}` : ""}
        onConfirm={buy} onCancel={() => setProduct(null)}>
        <p>The licence is issued to the company or person below and shown in your installation.</p>
        <div className="mt-4 space-y-3">
          <TextField label="Licensee (company or name)" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
          <TextField label="Licensee email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        {testMode && <TestCardPicker value={simulate} onChange={setSimulate} />}
        {testMode && <p className="mt-2 flex items-center gap-1.5 text-xs text-fg-subtle"><FlaskConical className="h-3.5 w-3.5" /> Test orders are fulfilled with test licences.</p>}
      </ConfirmDialog>
    </section>
  );
}
