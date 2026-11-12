import type { ReactNode } from "react";

export type DocPage = { slug: string; title: string; summary: string; body: ReactNode };

const Code = ({ children }: { children: string }) => (
  <pre className="my-4 overflow-x-auto rounded-lg border border-line bg-ink-950 p-4 text-[13px] leading-relaxed text-fg">
    <code>{children}</code>
  </pre>
);

export const DOCS: DocPage[] = [
  {
    slug: "getting-started",
    title: "Getting started",
    summary: "Create an account and add your first website in a minute.",
    body: (
      <>
        <h2>1. Create your account</h2>
        <p>
          Register with your email address and a password of at least 10 characters. We send a
          confirmation link — alerts are only delivered to confirmed addresses, so please click it.
        </p>
        <h2>2. Choose a plan</h2>
        <p>
          Your plan sets how many websites you can monitor and how often they are checked: Starter
          (3 sites, every 5 minutes), Pro (15 sites, every minute) or Business (50 sites, every 30
          seconds).
        </p>
        <h2>3. Add a monitor</h2>
        <p>
          On the dashboard choose <strong>Add monitor</strong>, give it a name, paste the URL (for
          example <code>https://www.example.ch</code>) and pick a check interval. That’s all —
          sensible defaults handle the rest. The first check runs within seconds.
        </p>
        <h2>4. Check your notification settings</h2>
        <p>
          Under <strong>Settings → Notifications</strong> decide which emails you receive and,
          optionally, send alerts to a different address such as a team mailbox.
        </p>
      </>
    ),
  },
  {
    slug: "monitors",
    title: "Monitors & checks",
    summary: "How checks work and what every monitor setting means.",
    body: (
      <>
        <h2>What a check does</h2>
        <p>
          Each check makes an HTTP request to your URL with a strict timeout. A check succeeds when
          the server answers with an expected status code (2xx and 3xx by default) and, if
          configured, the page contains your keyword.
        </p>
        <h2>Settings</h2>
        <ul>
          <li><strong>Interval</strong> — how often the site is checked. The shortest interval depends on your plan.</li>
          <li><strong>Timeout</strong> — how long to wait for an answer (default 10 s). Slower answers count as failures.</li>
          <li><strong>Expected status</strong> — comma-separated codes or ranges, e.g. <code>200-299,301</code>.</li>
          <li><strong>Keyword</strong> — optional text that must appear in the page body (GET only).</li>
          <li><strong>Confirm outage after</strong> — consecutive failures before an incident opens (default 2). Prevents alerts for one-off network blips.</li>
          <li><strong>Recover after</strong> — consecutive successes needed to close an incident (default 1).</li>
          <li><strong>Follow redirects</strong> — follow up to 5 redirects. Every redirect target is security-checked again.</li>
          <li><strong>Verify TLS</strong> — treat invalid or expired certificates as a failure.</li>
        </ul>
        <h2>Which addresses can be monitored?</h2>
        <p>
          Only public websites. For security, Uptivora refuses URLs that point to private networks
          (such as <code>10.0.0.0/8</code> or <code>192.168.0.0/16</code>), localhost, cloud
          metadata services, or that contain credentials. Self-hosted installations follow the same
          rules.
        </p>
        <h2>Pausing</h2>
        <p>
          Paused monitors keep their history but are not checked and do not count towards your
          plan’s active monitor limit.
        </p>
      </>
    ),
  },
  {
    slug: "notifications",
    title: "Alerts & notifications",
    summary: "When we email you, who receives alerts, and how duplicates are avoided.",
    body: (
      <>
        <h2>Events</h2>
        <ul>
          <li><strong>Outage</strong> — once, when an incident is confirmed by a second failed check.</li>
          <li><strong>Recovery</strong> — once, when the site is reachable again, including the outage duration.</li>
          <li><strong>SSL expiry</strong> — at your warning window (14 days by default), again at 7 days and 1 day, and on expiry.</li>
          <li><strong>Account emails</strong> — confirmations, password resets and security notices. These cannot be switched off.</li>
        </ul>
        <h2>Recipients</h2>
        <p>
          Alerts go to your confirmed account email and to up to five extra addresses, such as a
          team inbox or an on-call colleague. Each extra address receives a one-time confirmation
          email and gets alerts only after confirming — Uptivora can’t be used to email people who
          didn’t agree to it. Every alert has a one-click unsubscribe link.
        </p>
        <h2>No duplicates, no storms</h2>
        <p>
          Each alert has a unique key per event and recipient, so a server restart in the middle of
          sending can never produce a second email. A monitor that goes down and up more than five
          times within an hour stops emailing until it settles; the incidents are still recorded.
        </p>
        <h2>Delivery</h2>
        <p>
          Use <strong>Settings → Recipients → Send test alert</strong> to check that alerts arrive.
          The <strong>Recent alert emails</strong> list shows whether each email was sent, is being
          retried, or failed. Failed sends are retried with increasing delays for several hours.
        </p>
      </>
    ),
  },
  {
    slug: "account-security",
    title: "Account & security",
    summary: "Passwords, sessions and how we protect your account.",
    body: (
      <>
        <ul>
          <li>Passwords are stored with Argon2id, a modern memory-hard hashing algorithm.</li>
          <li>Sessions use secure, HttpOnly cookies and every change is protected against cross-site request forgery.</li>
          <li>You can see and sign out your active sessions under <strong>Settings → Security</strong>.</li>
          <li>Changing or resetting your password signs out all other sessions and sends you a notice.</li>
          <li>Repeated failed sign-in attempts are rate-limited.</li>
        </ul>
        <p>Uptivora uses no third-party trackers or analytics on any page.</p>
      </>
    ),
  },
  {
    slug: "self-hosting",
    title: "Self-hosting",
    summary: "Requirements and installation overview for the self-hosted edition.",
    body: (
      <>
        <h2>Requirements</h2>
        <ul>
          <li>A Linux server (1 vCPU / 1 GB RAM is enough for small installations)</li>
          <li>Docker Engine and Docker Compose</li>
          <li>A domain name pointing at the server (TLS certificates are issued automatically)</li>
          <li>An SMTP server or relay for sending alerts</li>
        </ul>
        <h2>Installation overview</h2>
        <Code>{`# 1. Unpack the release bundle and configure it
cp .env.example .env        # set your domain, SMTP and secrets

# 2. Put your licence file in place (optional — evaluation mode works without it)
cp ~/Downloads/your.uptivora-license license/uptivora.license

# 3. Start everything
docker compose up -d`}</Code>
        <p>
          Open your domain in a browser: the first account you create becomes the administrator.
          The full step-by-step guide ships with the release bundle.
        </p>
        <h2>No outbound dependencies</h2>
        <p>
          A self-hosted installation only connects to the websites you monitor and to your SMTP
          server. It never contacts Uptivora — not for licence checks, updates or telemetry.
        </p>
      </>
    ),
  },
  {
    slug: "licensing",
    title: "Licensing",
    summary: "How self-hosted licence files work and what they cover.",
    body: (
      <>
        <p>
          A self-hosted licence is a small text file signed with Uptivora’s Ed25519 private key.
          Your installation contains only the matching public key and verifies the signature
          locally. Any change to the file invalidates it.
        </p>
        <h2>What the licence file contains</h2>
        <ul>
          <li>A unique licence ID and the licensee’s name and email</li>
          <li>The edition (Starter or Professional) and its limits</li>
          <li>The issue date — and no expiry date</li>
        </ul>
        <h2>Without a licence</h2>
        <p>
          Installations without a valid licence run in evaluation mode with 3 monitors, 1 user and
          5-minute checks. Installing a licence lifts the limits immediately; removing it never
          deletes data — monitors above the limit are paused.
        </p>
        <h2>Licence vs. hosting vs. support</h2>
        <p>
          The licence covers the right to use the software and receive updates. Hosting it and
          support beyond the documentation are not part of the licence.
        </p>
      </>
    ),
  },
];

export function getDoc(slug: string): DocPage | undefined {
  return DOCS.find((d) => d.slug === slug);
}
