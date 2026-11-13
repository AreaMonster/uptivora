import Link from "next/link";
import { type ReactNode, Suspense } from "react";
import { ButtonLink } from "@/components/ui";
import { CheckLog } from "@/components/marketing/check-log";
import { PlanTable, TableSkeleton } from "@/components/marketing/catalogue";

const CHECK_FACTS: [string, string][] = [
  ["How often", "Every 5 minutes, every minute or every 30 seconds, depending on the plan."],
  ["What passes", "An HTTP status you expect (200–399 unless you say otherwise), within the timeout (10 s by default), optionally containing a keyword you choose."],
  ["What fails", "Timeouts, refused connections, DNS errors, broken TLS, an unexpected status code, a missing keyword."],
  ["Before you are told", "A failure is checked again 30 seconds later. Only a second failure opens an incident and sends an email."],
  ["Certificates", "Read on every HTTPS check. You are warned 14, 7 and 1 day before expiry, and when it has expired."],
  ["History", "Every check for 3 days, failed checks and everything around an outage for 30 days, hourly summaries for 400 days, incidents for good."],
];

const ALERT_FACTS: [string, string][] = [
  ["One email per event", "One when an outage is confirmed, one when the site is back, with how long it was down. Not one per failed check."],
  ["Up to five extra recipients", "A team inbox or a colleague on call. Each address confirms once before it receives anything."],
  ["Quiet during flapping", "A site that goes down and up more than five times in an hour stops sending email until it settles. The incidents are still recorded."],
];

const NOT_DONE = [
  "SMS, phone calls or chat notifications. Alerts are email only.",
  "Checks from several continents. Checks run from one location; a second check confirms every failure.",
  "Public status pages.",
  "AI of any kind, or analytics and trackers on this website.",
];

const FAQ: [string, string][] = [
  ["Can I cancel at any time?", "Yes. A plan runs until the end of the month you paid for. Your monitors and history stay in your account if you come back."],
  ["What does the self-hosted licence include?", "The complete application, its Docker setup and documentation, and every future update. It is verified on your server and never contacts us. One payment, no expiry."],
  ["Can it monitor internal systems?", "No. Uptivora refuses addresses in private networks, localhost and cloud metadata services, also in the self-hosted edition. It monitors what the public can reach."],
  ["Where does my data go?", "Into Uptivora's database and nowhere else. Alert emails go through Uptivora's mail server (or yours, when self-hosted). No third-party services are involved."],
];

export default function HomePage() {
  return (
    <>
      <section className="container-page grid grid-cols-[minmax(0,1fr)] gap-12 pb-20 pt-14 sm:pt-20 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-16">
        <div>
          <h1 className="text-[40px] font-semibold leading-[1.05] tracking-[-0.03em] sm:text-[56px]">
            Your website stopped answering at 14:02.
            <span className="block text-fg-subtle">You knew at 14:02.</span>
          </h1>
          <p className="mt-6 max-w-[34rem] text-[17px] leading-relaxed text-fg-muted">
            Uptivora requests your pages around the clock, confirms a failure with a second check,
            and sends you one email when a site goes down and one when it is back. It also tells
            you before an SSL certificate runs out.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
            <ButtonLink href="/register" size="lg">Start monitoring</ButtonLink>
            <span className="text-sm text-fg-muted">
              From CHF 5 a month, or{" "}
              <Link href="/self-hosted" className="link">run it on your own server</Link>.
            </span>
          </div>
        </div>
        <CheckLog />
      </section>

      <Section title="What a check is" id="checks">
        <Facts items={CHECK_FACTS} />
      </Section>

      <Section title="Alerts">
        <Facts items={ALERT_FACTS} />
      </Section>

      <Section title="Plans">
        <Suspense fallback={<TableSkeleton />}>
          <PlanTable />
        </Suspense>
        <p className="mt-4 text-sm text-fg-muted">
          Every plan has the same features; they differ in the number of websites and how often they
          are checked. <Link href="/pricing" className="link">Details</Link>
        </p>
      </Section>

      <Section title="Or run it yourself">
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="space-y-4 text-[15px] leading-relaxed text-fg-muted">
            <p>
              The self-hosted edition is the same software, sold once: CHF 99 for Starter, CHF 199
              for Professional. Your server, your database, your mail server.
            </p>
            <p>
              The licence is a signed file your installation checks by itself. No activation, no
              update check, no telemetry — the server only talks to the websites you monitor and
              to your SMTP server.
            </p>
            <Link href="/self-hosted" className="link inline-block text-sm">What the licence includes</Link>
          </div>
          <pre className="self-start overflow-x-auto rounded-[var(--radius-card)] bg-primary p-5 font-mono text-[13px] leading-6 text-on-primary">
            <code>
              <span className="opacity-50">$ </span>tar xzf uptivora-selfhosted.tar.gz{"\n"}
              <span className="opacity-50">$ </span>./install.sh{"\n"}
              <span className="opacity-50">$ </span>nano .env{"            "}<span className="opacity-50"># domain, SMTP</span>{"\n"}
              <span className="opacity-50">$ </span>docker compose up -d
            </code>
          </pre>
        </div>
      </Section>

      <Section title="What it does not do">
        <ul className="max-w-2xl divide-y divide-line border-y border-line">
          {NOT_DONE.map((t) => (
            <li key={t} className="py-3 text-[15px] text-fg-muted">{t}</li>
          ))}
        </ul>
      </Section>

      <Section title="Questions">
        <div className="max-w-2xl divide-y divide-line border-y border-line">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group py-4 [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer list-none items-baseline justify-between gap-4 font-medium">
                {q}
                <span className="font-mono text-fg-subtle group-open:hidden">+</span>
                <span className="hidden font-mono text-fg-subtle group-open:inline">−</span>
              </summary>
              <p className="mt-2 text-[15px] leading-relaxed text-fg-muted">{a}</p>
            </details>
          ))}
        </div>
        <p className="mt-4 text-sm text-fg-muted">
          More in the <Link href="/docs" className="link">documentation</Link>.
        </p>
      </Section>

      <section className="border-t border-line">
        <div className="container-page flex flex-col gap-6 py-16 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-2xl font-semibold tracking-[-0.02em]">Add your first website. It takes a minute.</p>
          <ButtonLink href="/register" size="lg">Create account</ButtonLink>
        </div>
      </section>
    </>
  );
}

function Section({ title, id, children }: { title: string; id?: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-16 border-t border-line">
      <div className="container-page grid grid-cols-[minmax(0,1fr)] gap-6 py-14 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-12">
        <h2 className="text-lg font-semibold tracking-[-0.01em]">{title}</h2>
        <div>{children}</div>
      </div>
    </section>
  );
}

function Facts({ items }: { items: [string, string][] }) {
  return (
    <dl className="grid gap-x-10 gap-y-6 sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="border-t border-line pt-3">
          <dt className="font-medium">{k}</dt>
          <dd className="mt-1 text-[15px] leading-relaxed text-fg-muted">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
