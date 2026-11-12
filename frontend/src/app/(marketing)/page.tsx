import Link from "next/link";
import {
  ArrowRight,
  BellRing,
  Check,
  Gauge,
  History,
  Lock,
  Server,
  ShieldCheck,
} from "lucide-react";
import { ButtonLink } from "@/components/ui";
import { ProductPreview } from "@/components/marketing/product-preview";

const FEATURES = [
  {
    icon: Gauge,
    title: "Uptime & response time",
    body: "Every site is checked on a fixed schedule — down to every 30 seconds. Response times are charted over 24 hours, 7, 30 and 90 days.",
  },
  {
    icon: BellRing,
    title: "Alerts that mean something",
    body: "An outage is confirmed by a second check before we email you, and you get exactly one alert when it goes down and one when it recovers.",
  },
  {
    icon: Lock,
    title: "SSL certificate expiry",
    body: "Uptivora reads the certificate on every HTTPS check and warns you well before it expires — no more surprise browser warnings.",
  },
  {
    icon: History,
    title: "Incident history",
    body: "Every outage is recorded with its start, end, duration and cause, so you can answer “how reliable were we last month?” in seconds.",
  },
  {
    icon: ShieldCheck,
    title: "Private by design",
    body: "No trackers, no third-party analytics, no data sold. Monitoring requests never reach private networks or internal services.",
  },
  {
    icon: Server,
    title: "Hosted or self-hosted",
    body: "Use our hosted service for a monthly fee, or buy a lifetime licence and run the exact same software on your own server.",
  },
];

const STEPS = [
  ["Add your website", "Paste a URL and choose how often to check it. That’s the whole setup."],
  ["We watch it around the clock", "Checks run from our servers with strict timeouts and redirect handling."],
  ["Get told when it matters", "Confirmed outages, recoveries and expiring certificates land in your inbox."],
];

const FAQ = [
  [
    "How is an outage detected?",
    "A check fails when the site does not answer within the timeout, the TLS handshake fails, or the HTTP status is not one you expect (2xx/3xx by default). A failure is re-checked before an incident is opened, which filters out one-off network blips.",
  ],
  [
    "Can I cancel at any time?",
    "Yes. Monthly plans can be cancelled at any time and stay active until the end of the period you paid for. Your history is kept if you come back.",
  ],
  [
    "What does the self-hosted licence include?",
    "A one-time payment gives you a perpetual licence for the full application — dashboard, admin area, monitoring workers, Docker deployment files and documentation — plus all future updates. It never phones home and works offline.",
  ],
  [
    "Do you use AI or third-party services to monitor my sites?",
    "No. Uptivora is conventional, open-source-based software. Checks are plain HTTP requests from our own servers and alerts are sent by our own mail server.",
  ],
];

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="grid-bg pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]" />
        <div className="pointer-events-none absolute -top-40 left-1/2 h-[480px] w-[900px] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,#14b8a62e,transparent)]" />
        <div className="container-page relative pb-16 pt-16 sm:pt-24">
          <div className="mx-auto max-w-3xl text-center">
            <p className="inline-flex items-center gap-2 rounded-full border border-line bg-ink-850/80 px-3 py-1 text-xs font-medium text-fg-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-up" />
              Uptime · Response time · SSL certificates
            </p>
            <h1 className="mt-6 text-balance text-4xl font-semibold tracking-tight text-fg sm:text-6xl">
              Know the moment your website goes down.
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-pretty text-base leading-relaxed text-fg-muted sm:text-lg">
              Uptivora checks your sites around the clock, charts their response times, watches
              their SSL certificates and emails you as soon as something breaks — and again when
              it’s fixed.
            </p>
            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
              <ButtonLink href="/register" size="lg">
                Start monitoring <ArrowRight className="h-4 w-4" />
              </ButtonLink>
              <ButtonLink href="/self-hosted" variant="secondary" size="lg">
                Self-host it instead
              </ButtonLink>
            </div>
            <p className="mt-4 text-xs text-fg-subtle">Plans from CHF 5 / month · cancel anytime</p>
          </div>
          <div className="mx-auto mt-14 max-w-5xl">
            <ProductPreview />
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="scroll-mt-20 border-t border-line/60 bg-ink-900/40 py-20">
        <div className="container-page">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold text-accent">Everything you need, nothing you don’t</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">
              Monitoring that stays out of your way until it’s needed
            </h2>
          </div>
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="card p-6">
                <div className="grid h-10 w-10 place-items-center rounded-lg bg-ink-700 text-accent ring-1 ring-line-strong">
                  <Icon className="h-5 w-5" aria-hidden />
                </div>
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-fg-muted">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-20">
        <div className="container-page">
          <h2 className="text-3xl font-semibold tracking-tight">Up and running in a minute</h2>
          <ol className="mt-10 grid gap-6 md:grid-cols-3">
            {STEPS.map(([title, body], i) => (
              <li key={title} className="relative pl-14">
                <span className="tnum absolute left-0 top-0 grid h-10 w-10 place-items-center rounded-full border border-line-strong bg-ink-800 text-sm font-semibold text-accent">
                  {i + 1}
                </span>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Two ways */}
      <section className="border-y border-line/60 bg-ink-900/40 py-20">
        <div className="container-page">
          <h2 className="text-3xl font-semibold tracking-tight">Two ways to use Uptivora</h2>
          <p className="mt-2 max-w-2xl text-fg-muted">
            The same monitoring engine powers both. Pick the one that fits how you work.
          </p>
          <div className="mt-10 grid gap-4 lg:grid-cols-2">
            <div className="card p-7">
              <p className="text-sm font-semibold text-up">Hosted</p>
              <h3 className="mt-1 text-xl font-semibold">We run it, you get alerts</h3>
              <p className="mt-2 text-sm text-fg-muted">Monthly subscription from CHF 5.</p>
              <ul className="mt-5 space-y-2.5 text-sm">
                {["Nothing to install or maintain", "Checks from our infrastructure", "Upgrade, downgrade or cancel anytime"].map((t) => (
                  <li key={t} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-up" />{t}</li>
                ))}
              </ul>
              <ButtonLink href="/pricing" variant="secondary" className="mt-7">
                See plans
              </ButtonLink>
            </div>
            <div className="card p-7">
              <p className="text-sm font-semibold text-accent">Self-hosted</p>
              <h3 className="mt-1 text-xl font-semibold">Your server, your data, forever</h3>
              <p className="mt-2 text-sm text-fg-muted">One-time licence from CHF 99.</p>
              <ul className="mt-5 space-y-2.5 text-sm">
                {["Perpetual licence, no renewals", "Works fully offline — never phones home", "All future updates included"].map((t) => (
                  <li key={t} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" />{t}</li>
                ))}
              </ul>
              <ButtonLink href="/self-hosted" variant="secondary" className="mt-7">
                About the licence
              </ButtonLink>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-20">
        <div className="container-page grid gap-10 lg:grid-cols-[1fr_1.6fr]">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight">Questions</h2>
            <p className="mt-2 text-fg-muted">
              More answers in the <Link href="/docs" className="text-accent hover:underline">documentation</Link>.
            </p>
          </div>
          <div className="divide-y divide-line rounded-[var(--radius-card)] border border-line bg-ink-800">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group px-6 py-5 [&_summary::-webkit-details-marker]:hidden">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">
                  {q}
                  <span className="text-fg-subtle transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="mt-3 text-sm leading-relaxed text-fg-muted">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="pb-24">
        <div className="container-page">
          <div className="card relative overflow-hidden px-8 py-12 text-center sm:px-16">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_bottom,#10b98122,transparent_60%)]" />
            <h2 className="relative text-3xl font-semibold tracking-tight">
              Stop finding out from your customers.
            </h2>
            <p className="relative mx-auto mt-3 max-w-xl text-fg-muted">
              Add your first website in under a minute.
            </p>
            <ButtonLink href="/register" size="lg" className="relative mt-8">
              Create your account <ArrowRight className="h-4 w-4" />
            </ButtonLink>
          </div>
        </div>
      </section>
    </>
  );
}
