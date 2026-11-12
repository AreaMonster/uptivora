import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Check, FlaskConical } from "lucide-react";
import { ButtonLink, Skeleton } from "@/components/ui";
import type { LicenceProduct, Plan, PublicConfig } from "@/lib/api";
import { cn, formatInterval, formatMoney } from "@/lib/format";
import { serverFetch } from "@/lib/server-api";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Simple monthly plans for hosted monitoring, or a one-time lifetime licence to self-host.",
};

const FEATURED = "pro";

export default function PricingPage() {
  return (
    <div className="container-page py-16 sm:py-20">
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-4xl font-semibold tracking-tight">Simple, honest pricing</h1>
        <p className="mt-4 text-fg-muted">
          Every plan includes uptime and response-time monitoring, SSL certificate checks, email
          alerts and full incident history. Prices in Swiss francs.
        </p>
      </div>
      <Suspense fallback={<PricingSkeleton />}>
        <PricingContent />
      </Suspense>
      <div className="mx-auto mt-16 max-w-3xl text-center text-sm text-fg-muted">
        Prefer to run it on your own server?{" "}
        <Link href="/self-hosted" className="font-medium text-accent hover:underline">
          Read what the lifetime self-hosted licence includes
        </Link>
        .
      </div>
    </div>
  );
}

async function PricingContent() {
  const [catalogue, config] = await Promise.all([
    serverFetch<{ plans: Plan[]; licences: LicenceProduct[] }>("/api/public/plans"),
    serverFetch<PublicConfig>("/api/public/config"),
  ]);
  if (!catalogue) {
    return (
      <p className="mt-12 text-center text-fg-muted">
        Prices are temporarily unavailable. Please try again in a moment.
      </p>
    );
  }
  return (
    <>
      {config?.billing_test_mode && (
        <div className="mx-auto mt-8 flex max-w-2xl items-center gap-3 rounded-xl border border-warn/30 bg-warn-soft px-4 py-3 text-sm text-[#fde68a]">
          <FlaskConical className="h-4 w-4 shrink-0" />
          <p>
            <strong>Test mode:</strong> payments are simulated while we finish setting up billing.
            No real money is charged.
          </p>
        </div>
      )}
      <div className="mt-12 grid gap-4 lg:grid-cols-3">
        {catalogue.plans.map((plan) => {
          const featured = plan.code === FEATURED;
          return (
            <div
              key={plan.code}
              className={cn(
                "card relative flex flex-col p-7",
                featured && "border-up/50 ring-1 ring-up/30",
              )}
            >
              {featured && (
                <span className="absolute -top-3 left-7 rounded-full bg-up px-3 py-0.5 text-xs font-semibold text-ink-950">
                  Most popular
                </span>
              )}
              <h2 className="text-lg font-semibold">{plan.name}</h2>
              <p className="mt-1 min-h-10 text-sm text-fg-muted">{plan.description}</p>
              <p className="mt-6 flex items-baseline gap-1.5">
                <span className="tnum text-4xl font-semibold tracking-tight">
                  {formatMoney(plan.price_cents, plan.currency)}
                </span>
                <span className="text-sm text-fg-muted">/ {plan.interval}</span>
              </p>
              <ul className="mt-6 flex-1 space-y-3 text-sm">
                {[
                  `${plan.max_monitors} monitored websites`,
                  `Checks every ${formatInterval(plan.min_interval_seconds)}`,
                  "SSL certificate expiry warnings",
                  "Email alerts on outage & recovery",
                  "Response-time charts & incident history",
                ].map((f) => (
                  <li key={f} className="flex gap-2.5">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-up" aria-hidden />
                    {f}
                  </li>
                ))}
              </ul>
              <ButtonLink
                href={`/register?plan=${plan.code}`}
                variant={featured ? "primary" : "secondary"}
                className="mt-8"
              >
                Choose {plan.name}
              </ButtonLink>
            </div>
          );
        })}
      </div>

      {catalogue.licences.length > 0 && (
        <div className="mt-20">
          <h2 className="text-center text-2xl font-semibold tracking-tight">
            Self-hosted lifetime licences
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-center text-sm text-fg-muted">
            Pay once, run it on your own infrastructure forever, including all future updates.
          </p>
          <div className="mx-auto mt-8 grid max-w-4xl gap-4 md:grid-cols-2">
            {catalogue.licences.map((lic) => (
              <div key={lic.code} className="card flex flex-col p-7">
                <h3 className="text-lg font-semibold">{lic.name}</h3>
                <p className="mt-1 text-sm text-fg-muted">{lic.description}</p>
                <p className="mt-5 flex items-baseline gap-1.5">
                  <span className="tnum text-3xl font-semibold">
                    {formatMoney(lic.price_cents, lic.currency)}
                  </span>
                  <span className="text-sm text-fg-muted">one-time</span>
                </p>
                <ul className="mt-5 space-y-2.5 text-sm">
                  <li className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 text-accent" />
                    {lic.limits.max_monitors ? `${lic.limits.max_monitors} monitors` : "Unlimited monitors"}
                  </li>
                  <li className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 text-accent" />
                    {lic.limits.max_users ? `${lic.limits.max_users} users` : "Unlimited users"}
                  </li>
                  <li className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 text-accent" />
                    Checks every {formatInterval(lic.limits.min_interval_seconds)}
                  </li>
                </ul>
                <ButtonLink href="/self-hosted" variant="secondary" className="mt-7">
                  Learn more
                </ButtonLink>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function PricingSkeleton() {
  return (
    <div className="mt-12 grid gap-4 lg:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card space-y-4 p-7">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-28 w-full" />
        </div>
      ))}
    </div>
  );
}
