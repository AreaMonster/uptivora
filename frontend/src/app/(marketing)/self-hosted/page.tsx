import type { Metadata } from "next";
import Link from "next/link";
import { Check, Minus } from "lucide-react";
import { ButtonLink } from "@/components/ui";

export const metadata: Metadata = {
  title: "Self-hosted licence",
  description:
    "Buy Uptivora once and run it on your own server forever. Perpetual licence, offline verification, all updates included.",
};

const INCLUDED = [
  ["The complete application", "Customer dashboard, administrator dashboard, API and monitoring workers — the same software that runs our hosted service."],
  ["Deployment kit", "Docker Compose files, database setup and migrations, configuration examples and a backup service."],
  ["A perpetual licence", "Use it for as long as you like. No renewals, no subscriptions, no expiry date in the licence file."],
  ["All future updates", "Every new self-hosted release is included for the lifetime of the product. You decide when to upgrade."],
  ["Offline operation", "The licence is verified locally with a cryptographic signature. The software never contacts our servers."],
  ["Documentation", "Installation, SMTP setup, backups, upgrades and troubleshooting guides."],
];

const NOT_INCLUDED = [
  ["Hosting", "You provide the server (a small Linux VPS is enough), domain, TLS certificate and SMTP server."],
  ["Support and SLAs", "Self-service documentation is included. Priority support or an installation service are optional, separate offers."],
  ["A hosted account", "A self-hosted licence does not include a subscription to our hosted service."],
];

const EDITIONS = [
  { name: "Starter Self-Hosted", price: "CHF 99", rows: ["25 monitored websites", "3 user accounts", "Checks every 60 seconds"] },
  { name: "Professional Self-Hosted", price: "CHF 199", rows: ["Unlimited monitored websites", "Unlimited user accounts", "Checks every 30 seconds"] },
];

export default function SelfHostedPage() {
  return (
    <div className="container-page py-16 sm:py-20">
      <div className="max-w-3xl">
        <p className="text-sm font-semibold text-accent">Self-hosted Uptivora</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight">
          Buy it once. Run it on your own server. Forever.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-fg-muted">
          The self-hosted edition is the full Uptivora platform, licensed for a one-time payment.
          Your database, your monitoring workers, your users, your data — with no monthly fees and
          no dependency on us.
        </p>
      </div>

      <div className="mt-12 grid gap-4 md:grid-cols-2">
        {EDITIONS.map((e) => (
          <div key={e.name} className="card p-7">
            <h2 className="font-semibold">{e.name}</h2>
            <p className="mt-3 flex items-baseline gap-1.5">
              <span className="tnum text-3xl font-semibold">{e.price}</span>
              <span className="text-sm text-fg-muted">one-time</span>
            </p>
            <ul className="mt-5 space-y-2 text-sm">
              {e.rows.map((r) => (
                <li key={r} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 text-accent" />{r}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="mt-4 text-sm text-fg-subtle">
        Licences are sold through your Uptivora account. Online checkout opens soon — until then,
        prices shown are indicative.
      </p>

      <section className="mt-16 grid gap-10 lg:grid-cols-2">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">What lifetime access includes</h2>
          <ul className="mt-6 space-y-5">
            {INCLUDED.map(([t, d]) => (
              <li key={t} className="flex gap-3">
                <Check className="mt-1 h-5 w-5 shrink-0 text-up" aria-hidden />
                <div>
                  <p className="font-medium">{t}</p>
                  <p className="mt-0.5 text-sm leading-relaxed text-fg-muted">{d}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">What it doesn’t include</h2>
          <p className="mt-2 text-sm text-fg-muted">
            The licence covers the software. Running it, and help beyond the documentation, are
            separate things:
          </p>
          <ul className="mt-6 space-y-5">
            {NOT_INCLUDED.map(([t, d]) => (
              <li key={t} className="flex gap-3">
                <Minus className="mt-1 h-5 w-5 shrink-0 text-fg-subtle" aria-hidden />
                <div>
                  <p className="font-medium">{t}</p>
                  <p className="mt-0.5 text-sm leading-relaxed text-fg-muted">{d}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="card mt-16 p-8">
        <h2 className="text-xl font-semibold">How the licence works</h2>
        <div className="mt-4 grid gap-6 text-sm leading-relaxed text-fg-muted md:grid-cols-3">
          <p>
            After purchase you receive a small licence file signed with our Ed25519 key. You copy it
            into your installation or upload it in the admin dashboard.
          </p>
          <p>
            Your installation checks the signature locally against our public key. There is no
            activation server, no hardware fingerprinting and no internet connection required.
          </p>
          <p>
            The licence states your edition and limits and never expires. If it were ever removed,
            the software keeps your data and falls back to evaluation limits — nothing is deleted.
          </p>
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <ButtonLink href="/docs/self-hosting" variant="secondary">Read the installation guide</ButtonLink>
          <ButtonLink href="/docs/licensing" variant="ghost">Licence details</ButtonLink>
        </div>
      </section>

      <p className="mt-10 text-sm text-fg-subtle">
        Requirements: a Linux server with Docker and Docker Compose, 1 vCPU and 1 GB RAM for small
        installations. See <Link href="/docs/self-hosting" className="text-accent hover:underline">self-hosting</Link>.
      </p>
    </div>
  );
}
