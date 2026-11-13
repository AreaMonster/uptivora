import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { LicenceTable, PlanTable, TableSkeleton } from "@/components/marketing/catalogue";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Monthly plans for hosted monitoring, or a one-time licence to run Uptivora on your own server.",
};

const INCLUDED = [
  "HTTP(S) checks with your expected status codes, timeout and keyword",
  "Response-time charts for 24 hours, 7, 30 and 90 days",
  "SSL certificate expiry warnings",
  "Email alerts on outage and recovery, to you and up to five more addresses",
  "Incident history with start, end, duration and cause, and notes",
];

export default function PricingPage() {
  return (
    <div className="container-page py-14 sm:py-20">
      <h1 className="max-w-2xl text-[40px] font-semibold leading-tight tracking-[-0.03em]">Pricing</h1>
      <p className="mt-4 max-w-2xl text-[17px] leading-relaxed text-fg-muted">
        Monthly, in Swiss francs, cancel whenever you like. The plans differ only in how many
        websites you can monitor and how often they are checked.
      </p>

      <div className="mt-10">
        <Suspense fallback={<TableSkeleton />}>
          <PlanTable chooseLinks />
        </Suspense>
      </div>

      <div className="mt-14 grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
        <h2 className="text-lg font-semibold">Every plan includes</h2>
        <ul className="max-w-2xl divide-y divide-line border-y border-line">
          {INCLUDED.map((t) => (
            <li key={t} className="py-3 text-[15px] text-fg-muted">{t}</li>
          ))}
        </ul>

        <h2 className="text-lg font-semibold">Billing</h2>
        <div className="max-w-2xl space-y-3 text-[15px] leading-relaxed text-fg-muted">
          <p>
            Upgrades apply immediately; you pay the difference for the rest of the month.
            Downgrades and cancellations take effect at the end of the period you paid for.
          </p>
          <p>
            If you move to a smaller plan, the most recently added monitors above its limit are
            paused, never deleted, and resume by themselves when there is room again.
          </p>
        </div>

        <h2 className="text-lg font-semibold">Self-hosted</h2>
        <div>
          <p className="mb-6 max-w-2xl text-[15px] leading-relaxed text-fg-muted">
            One payment, no expiry, all future updates. You run it on your own server.{" "}
            <Link href="/self-hosted" className="link">What the licence includes</Link>
          </p>
          <Suspense fallback={<TableSkeleton />}>
            <LicenceTable />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
