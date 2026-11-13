# Development Roadmap

Each phase ends with: code merged, automated tests passing, docs updated, and a short
"done / not done" note below. A feature is only ticked when it is implemented **and** tested.

## Phase 1 — Architecture, schema, project structure ✅ (2026-11-12)

- [x] Architecture, risks, editions and licensing design (`docs/`)
- [x] Monorepo layout, dev services (Postgres 17 + Mailpit) via Docker Compose
- [x] Settings with `*_FILE` secrets, production safety checks (secret strength, https,
      test billing refused in prod, dev mode refused on public hosts)
- [x] Full database schema (22 tables) + Alembic migration with seeded plans & licence products
- [x] Argon2id password hashing, token hashing, password policy
- [x] SSRF URL validator + public-only DNS resolution
- [x] Ed25519 licence format, offline verifier, offline `licensegen` CLI (keygen/issue/verify)
- [x] 141 automated tests (schema invariants against real PostgreSQL)

Not done in Phase 1 by design: HTTP routes, frontend, worker.

## Phase 2 — Authentication, frontend, customer dashboard ✅ (2026-11-12)

Backend
- [x] Auth API: register, login, logout, `/me`, email verification, forgot/reset password;
      server-side sessions (hashed tokens, idle + absolute expiry), per-session CSRF token,
      Origin / Sec-Fetch-Site guard, uniform login errors, Postgres fixed-window rate limits
- [x] Account API: profile + time zone, password change (revokes other sessions), session
      list/revoke, notification preferences, incident list, account deletion
- [x] `LimitsProvider` (`app/limits.py`): hosted = plan per user, self-hosted = licence per
      installation (unlicensed evaluation fallback); race-safe limit checks
- [x] Monitor API: CRUD, pause/resume, SSRF validation incl. DNS, plan interval/count limits,
      24 h/7 d/30 d/90 d uptime from raw results + hourly rollups, chart series, recent checks
- [x] Email outbox + SMTP sender (aiosmtplib), retry with back-off; worker process
- [x] Self-hosted: first account becomes admin, sign-up closed afterwards (admin-controlled)
- [x] `python -m app.cli create-user`, `python -m app.devseed` (demo data, dev only)

Frontend (Next.js 16, Tailwind 4, Recharts, self-hosted Inter font)
- [x] Design system, homepage, pricing (live plans, TEST MODE banner), self-hosted licence
      page, documentation (6 pages)
- [x] Login, register (self-hosted setup mode), forgot/reset password, email confirmation
- [x] App shell, dashboard, add/edit monitor, monitor detail with charts, incidents, settings
- [x] Verified in a browser on desktop and 375 px mobile

Tests: 177 backend tests (auth, CSRF, rate limits, SSRF, ownership isolation, plan and
licence limits, statistics, outbox delivery via Mailpit).
Not yet: browser E2E tests (planned with Playwright in Phase 9); plan selection/checkout
(Phase 6); invitations (Phase 7).

## Phase 3 — Monitoring engine and background jobs ✅ (2026-11-12)

- [x] `GuardedNetworkBackend` (httpcore): resolves DNS itself, refuses if any address is not
      public, dials only the validated IP; TLS SNI/verification still use the hostname
      (DNS-rebinding safe); no proxies from the environment; keep-alive disabled
- [x] Check executor (`app/engine/checker.py`): total deadline incl. redirects, manual
      redirects (max 5) re-validated on every hop, HTTPS→HTTP downgrade refused, expected
      status ranges, keyword search (1 MiB body cap), TLS certificate capture (expiry, issuer),
      error classification (timeout, dns, tls, connection, protocol, blocked, …)
- [x] Scheduler (`app/engine/scheduler.py`): `FOR UPDATE SKIP LOCKED` leases (120 s),
      concurrency limit, max 2 concurrent checks per host, suspended owners skipped,
      graceful drain, crash recovery via lease expiry, horizontal scaling
- [x] State machine (`app/engine/state.py`): confirmation re-check after 30 s, configurable
      down/recovery thresholds, one incident per outage starting at the first failure
- [x] Outage / recovery alert emails queued in the same transaction (deduplicated), only to
      confirmed addresses and respecting preferences *(moved forward from Phase 4)*
- [x] Housekeeping under advisory locks: hourly rollups (incl. p95), retention purge,
      SSL expiry warnings (window / 7 d / 1 d / expired, each sent once), worker heartbeats
- [x] Verified live: real check of https://example.com (status, latency, certificate) and a
      real outage → incident → alert email delivered via SMTP

Tests: 216 total. New: 14 executor tests against real local HTTP/HTTPS servers (redirects,
timeouts, TLS, SSRF via redirect, DNS rebinding, mixed DNS answers), state-machine property
test, scheduler lifecycle, lease/double-claim, 3 concurrent workers × 300 monitors (each checked
exactly once), rollups, retention, SSL dedupe, advisory locks.
Not yet: checks from multiple locations (roadmap item), 10k-monitor load test (Phase 9).

## Phase 4 — Email notifications and incident management ✅ (2026-11-13)

- [x] Alert contacts: up to 5 extra recipients per account, each confirmed via a one-time link
      (public confirm page; addresses never receive alerts unconfirmed); resend, pause, remove
- [x] Account-email switch (`send_to_account_email`) replaces the unconfirmed `alert_email`
      field (migrated to unconfirmed contacts by migration 0002)
- [x] Signed (HMAC) unsubscribe links: confirmation page link in every alert body, RFC 8058
      one-click `List-Unsubscribe` header; recipient opt-out sticks until re-confirmed
- [x] Alert fan-out: one outbox row per event and recipient (account email keeps the original
      dedupe key so upgrades never re-send), flapping protection (> 5 incidents/hour → muted)
- [x] Test alert button and delivery log (sent / retrying / failed) in Settings
- [x] Email templates: detail table, coloured accent per event, footer with settings and
      unsubscribe links, all values HTML-escaped, no remote content, header-injection safe
- [x] Incidents: status filters, cursor pagination, 30-day summary (count, open, downtime,
      MTTR), detail page with timeline (start, alerts, acknowledgement, recovery), checks during
      the outage, acknowledge / un-acknowledge, notes
- [x] Fixed: long headers were RFC 2047-encoded by aiosmtplib's re-serialisation (messages
      are now sent as raw bytes with a 998-char policy)
- [x] Verified live with Mailpit: contact confirmation, test alerts, unsubscribe from the email

Tests: 234 total (+ contacts, confirmation, unsubscribe incl. one-click, isolation, limits,
test alert, delivery log, fan-out, flapping, incidents API, template escaping, SMTP headers).

## Phase 5 — Administrator dashboard ✅ (2026-11-12)

- [x] Separate admin area (`/admin`, own layout with amber accent) — only for admins; admins
      also get an "Admin" link in the app sidebar
- [x] Overview: users, subscriptions, MRR (TEST MODE revenue shown separately), monitors,
      checks per minute, failed checks, alert emails, 24 h checks chart, recent incidents and
      warnings, health banner
- [x] System health: database (latency, size, connections, largest tables), workers with
      heartbeats, overdue checks, email queue / SMTP, disk, load; issues called out in plain words
- [x] Users: search, filters, pagination, read-only support view (no "log in as"), suspend /
      reactivate (revokes sessions), grant / remove admin, sign out all sessions; self-lockout
      and last-admin protection
- [x] Monitor moderation: search all monitors, pause with an internal reason (owner cannot
      resume), lift admin pauses only
- [x] Plan editor (price, limits, visibility, new plans) and self-hosted licence prices/limits;
      every change in the audit log with before/after values
- [x] Application log (buffered handler → `system_events`, flushed by API and worker) and
      audit log with filters; runtime setting for open sign-up (self-hosted)
- [x] Development-only tools (never mounted in production, re-checked per request): test
      accounts with TEST subscriptions, DEV-signed test licences (no key material returned)
- [x] Fixed during testing: log handler deadlock (own lock shadowed `logging.Handler.lock`)
- [x] Verified in the browser as the dev admin on desktop and 375 px mobile

Tests: 249 backend tests — new: RBAC test that discovers every `/api/admin` route from the
OpenAPI schema (anonymous → 401, user → 403), overview/health, user management, monitor
moderation, plan and licence editors, settings, event log, dev tools on/off.

## Phase 6 — Subscriptions and TEST MODE payment simulator ✅ (2026-11-12)

- [x] `PaymentProvider` interface (`app/billing/providers.py`): `TestModeProvider` (simulated
      success/decline, never touches the network, every payment stored with `is_test`),
      `ManualProvider` (admin-assigned plans), `StripeProvider` skeleton — disabled
- [x] Stripe webhook signature verification (`t=…,v1=…`, HMAC-SHA256, 5-minute replay window,
      multiple signatures) and idempotent event log (`webhook_events`); endpoint inactive
      until the provider is enabled
- [x] Subscribe (full month), upgrade (immediate, prorated for the rest of the period),
      downgrade (scheduled for period end, can be undone), cancel (works until period end),
      resume; past-due subscriptions cannot change plans until paid
- [x] Worker billing job (advisory lock, every 10 min): renewals with scheduled downgrades,
      failed renewal → past due with 7-day grace and daily retries, expiry, catch-up after
      downtime; manual plans expire silently
- [x] Monitor rebalancing on every limit change: newest monitors over the limit paused
      (`plan_limit`, never deleted), resumed automatically when there is room again,
      intervals raised to the plan minimum
- [x] Billing emails (receipt, payment failed, subscription ended, licence ready) prefixed
      `[TEST]` with a "no money was charged" note in test mode
- [x] Self-hosted licence store: order + TEST payment → admin attaches the offline-signed file
      (verified with the embedded public keys, edition must match, a licence can only serve
      one order) → customer download; refunds of test orders
- [x] UI: Billing page (current plan, plan cards with upgrade/downgrade, test checkout with
      success/decline card, past-due retry, "fail next renewal" test switch, payment history,
      licence store and downloads), persistent TEST MODE bar in the app, sign-up with
      `?plan=` continues to checkout; admin "Billing & licences" (orders, fulfilment, payments)
      and "Assign plan" on users
- [x] Verified in the browser: declined + successful prorated upgrade, licence purchase,
      admin fulfilment with a licensegen-signed file, customer download verified offline

Tests: 263 backend tests (+14: lifecycle, proration, decline, downgrade pausing, cancel/
resume/expiry with auto-resume, past due/retry/grace, disabled/self-hosted, manual plans,
licence store end to end, Stripe signatures, webhook idempotency, nothing deleted).
Not yet: real payment provider (requires a merchant account — Stripe adapter is a stub),
VAT handling and invoices as PDF (Phase 10 / legal review).

## Phase 7 — Self-hosted edition and offline licence verification ✅ (2026-11-13)

- [x] First run: the first account becomes administrator ("Set up your installation");
      sign-ups are serialised with a Postgres advisory lock, so two simultaneous first
      registrations can never both become admin (tested)
- [x] Licence installation in the admin dashboard (upload or paste, verified offline before it
      is stored, history kept) or as a file (`UPTIVORA_LICENSE_PATH`, takes precedence);
      licence page with licensee, edition, "never expires", limits vs. usage, dev-key warning
- [x] Installation-wide limit enforcement (`app/enforcement.py`): on install/remove/replace and
      every 5 minutes in the worker — newest monitors over the limit paused, resumed when there
      is room, intervals raised; nothing deleted
- [x] Invitations: admin invites by email (user/admin), pending accounts count towards the
      licence user limit and cannot sign in, single-use 7-day link to choose a password
      (confirms the email), resend/revoke; open sign-up toggle stays available
- [x] Setup checklist on the admin overview (worker, SMTP, licence, first monitor, team)
- [x] Licensee / evaluation mode shown in the app sidebar; no billing UI in self-hosted
- [x] No phone home: static test (network clients only in the checker and mailer, no
      trackers/analytics/external fonts in the frontend), runtime test recording every
      outbound connection during a full self-hosted session (only the local database), and
      Next.js build telemetry disabled for every npm script (`frontend/scripts/next.mjs`)
- [x] Fixed: the dev seed's admin password violated the app's own password policy
- [x] Verified in a separate self-hosted instance (own database, API, worker and production
      web build): setup, evaluation banner, licence install, invitation via Mailpit, accept

Tests: 275 backend tests (+12).

## Phase 8 — Docker deployment and documentation ✅ (2026-11-13)

- [x] Multi-stage images: `backend/Dockerfile` (API + worker, Python 3.12 slim, pinned by
      `backend/constraints.txt`, uid 10001, byte-compiled, no dev seed/keys/tests) and
      `frontend/Dockerfile` (Next.js standalone, Node 24 alpine, `node` user, telemetry off,
      npm removed from the runtime image)
- [x] `deploy/selfhosted/` (the customer bundle) and `deploy/hosted/`: read-only containers,
      `cap_drop: ALL`, `no-new-privileges`, database on an `internal: true` network, Docker
      secrets for DB password / secret key / SMTP password (`UPTIVORA_DATABASE_PASSWORD_FILE`
      is new), migrations as a one-shot service before API and workers start
- [x] Caddy: automatic HTTPS (`UPTIVORA_TLS=auto`) or its own CA for intranets (`internal`),
      `/api/*` to the API, rest to the web app, HSTS, admin API off; the API trusts
      `X-Forwarded-For` only from the edge network subnet
- [x] Backup service: nightly `pg_dump` with rotation; `now`, `list`, `verify` (restore into a
      scratch database) and `restore` commands
- [x] `deploy/release/build.sh`: refuses dirty trees and tracked keys, builds both images,
      checks the API image for dev files, writes the offline bundle + SHA256SUMS
- [x] Customer docs (`docs/selfhosted/`): install, SMTP, licence, backups, upgrade,
      troubleshooting. Operator docs (`docs/operations/`): hosted deployment, VPS hardening,
      firewall incl. egress rules, release process (key ceremony: `LICENSE_KEY_OPERATIONS.md`)
- [x] Verified on Docker Desktop: self-hosted stack over HTTPS (first-admin sign-up,
      monitor checked from the worker, email via SMTP, dev-signed licence rejected by the
      production image, backup → verify → wipe → restore), hosted stack with two workers and
      the operator CLI, and a full release build

### Redesign (2026-11-13)

The first UI used the stock dark-navy/teal "AI dashboard" look. Replaced with a paper-and-ink
system: IBM Plex Sans/Mono (self-hosted), warm off-white surfaces, near-black type, hairline
rules, 3–4 px corners, colour only for state; light and dark follow the OS. Top navigation
instead of an icon sidebar, ruled figures instead of KPI cards, tables instead of card grids.
The landing page explains one real outage as a check log and the two emails it causes, and
says plainly what the product does not do. Alert email subjects no longer carry emoji.

## Phase 9 — Security and performance testing

- Threat model review; SSRF test matrix; auth/session/CSRF tests; dependency audit
  (`pip-audit`, `npm audit`); static analysis (ruff S rules, bandit, semgrep OSS)
- Headers/CSP verification, rate-limit verification, ZAP baseline scan (OSS)
- Load: 10 000 monitors at 60 s on a 2 vCPU VPS; DB size projections; query plans

## Phase 10 — Production-readiness review

- Checklist: secrets, backups tested by restore, monitoring of the monitor (external
  heartbeat), log rotation, alerting, incident runbooks
- Legal items that need a professional, not code: Terms, Privacy Policy (revDSG/GDPR),
  DPA, licence agreement wording, VAT handling, payment provider onboarding
- Release v1.0: hosted launch with TEST billing → switch to real provider once the account
  exists; self-hosted bundle publication
