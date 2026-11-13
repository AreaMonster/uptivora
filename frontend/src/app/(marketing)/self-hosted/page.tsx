import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { LicenceTable, TableSkeleton } from "@/components/marketing/catalogue";

export const metadata: Metadata = {
  title: "Self-hosted licence",
  description:
    "Buy Uptivora once and run it on your own server. Perpetual licence, verified offline, all updates included.",
};

const INCLUDED: [string, string][] = [
  ["The whole application", "Dashboard, administration, API and monitoring workers. The same code that runs the hosted service."],
  ["Deployment", "Docker Compose stack with automatic HTTPS (Caddy), PostgreSQL, nightly backups with a restore tool, and database migrations that run on start."],
  ["Every future update", "New versions are included for as long as the product exists. Nothing updates itself; you decide when."],
  ["Documentation", "Installation, email setup, licence, backups and restore, upgrades, troubleshooting."],
];

const NOT_INCLUDED: [string, string][] = [
  ["The server", "A small Linux machine with Docker (1 CPU, 1 GB RAM covers a few hundred monitors), a domain name and an SMTP server for alerts."],
  ["Support beyond the documentation", "Installation help or priority support can be arranged separately."],
  ["A hosted account", "The licence is for running the software yourself, not for the hosted service."],
];

const HOW: [string, string][] = [
  ["You receive a file", "A few lines of text signed with Uptivora's Ed25519 key, naming you, your edition and its limits. No expiry date."],
  ["Your server checks it", "Against the public key built into the software. No activation server, no hardware fingerprint, no internet connection."],
  ["Nothing is ever deleted", "Without a valid licence the installation falls back to evaluation limits: monitors above them are paused, not removed."],
];

export default function SelfHostedPage() {
  return (
    <div className="container-page py-14 sm:py-20">
      <h1 className="max-w-3xl text-[40px] font-semibold leading-[1.08] tracking-[-0.03em]">
        Pay once. Run it on your own server.
      </h1>
      <p className="mt-5 max-w-2xl text-[17px] leading-relaxed text-fg-muted">
        The self-hosted edition is the complete Uptivora, licensed for a one-time payment. It runs
        on your hardware, keeps its data in your database and sends alerts through your mail
        server. It never contacts us — not for the licence, not for updates, not for statistics.
      </p>

      <div className="mt-10">
        <Suspense fallback={<TableSkeleton />}>
          <LicenceTable />
        </Suspense>
        <p className="mt-3 text-sm text-fg-subtle">
          Licences are sold through your Uptivora account. Online checkout is not open yet.
        </p>
      </div>

      <div className="mt-14 grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
        <h2 className="text-lg font-semibold">Included</h2>
        <Rows items={INCLUDED} />
        <h2 className="text-lg font-semibold">Not included</h2>
        <Rows items={NOT_INCLUDED} />
        <h2 className="text-lg font-semibold">How the licence works</h2>
        <Rows items={HOW} />
        <h2 className="text-lg font-semibold">Installation</h2>
        <div className="max-w-2xl">
          <pre className="overflow-x-auto rounded-[var(--radius-card)] bg-primary p-5 font-mono text-[13px] leading-6 text-on-primary">
            <code>{`./install.sh          # settings file, secrets, images
nano .env             # domain and SMTP server
docker compose up -d  # HTTPS certificate, database, app`}</code>
          </pre>
          <p className="mt-3 text-sm text-fg-muted">
            Then open your domain; the first account becomes the administrator.{" "}
            <Link href="/docs/self-hosting" className="link">Installation guide</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

function Rows({ items }: { items: [string, string][] }) {
  return (
    <dl className="max-w-2xl divide-y divide-line border-y border-line">
      {items.map(([k, v]) => (
        <div key={k} className="grid gap-1 py-3.5 sm:grid-cols-[200px_1fr] sm:gap-6">
          <dt className="font-medium">{k}</dt>
          <dd className="text-[15px] leading-relaxed text-fg-muted">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
