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

## Phase 4 — Email notifications and incident management

- (SMTP sender, outbox back-off, down/recovery/SSL alerts and preferences are already done)
- Separate alert address with its own confirmation flow; multiple recipients per account
- Delivery status in the UI (sent / failed / retrying) and a "send test alert" button
- Template polish, plain-text/HTML preview tests
- Incident history UI, incident detail with timeline
- Tests: Mailpit-backed integration test, dedupe/idempotency tests

## Phase 5 — Administrator dashboard

- Admin API + UI: KPIs (customers, active/cancelled subscriptions, monitors, checks/min),
  server/DB/worker health, recent incidents, system events log, audit log
- User management (search, suspend, role, impersonation-free support view), plan editor,
  usage limits, pause abusive monitors
- Development-only tools: create test accounts, issue **dev-key** test licences
- Tests: RBAC tests on every admin route (user → 403)

## Phase 6 — Subscription management and TEST MODE payment simulator

- `PaymentProvider` interface; `TestModeProvider` (simulated checkout, success/failure
  toggles, renewal, `is_test` everywhere, persistent TEST MODE banner, `[TEST]` emails)
- Subscribe, upgrade (immediate, prorated in test mode), downgrade (period end, excess
  monitors paused), cancel / resume, renewal + past_due + expiry jobs
- Self-hosted licence storefront (hosted edition): order → TEST payment → admin attaches
  signed licence → customer download
- Stripe adapter skeleton with webhook signature verification + idempotency, **disabled**
- Tests: full subscription lifecycle, limit changes, webhook signature tests

## Phase 7 — Self-hosted edition and offline licence verification

- First-run setup wizard (create owner admin), invitations, public sign-up toggle
- Licence install (file in volume or upload in admin), status page, licensee shown in footer
- Unlicensed evaluation limits; over-limit monitors paused (never deleted)
- Verify there are **zero** outbound connections other than monitored sites and SMTP
  (test that runs the stack with egress blocked)

## Phase 8 — Docker deployment and documentation

- Multi-stage Dockerfiles (non-root, read-only FS, no dev keys / tools in images)
- `deploy/hosted/` and `deploy/selfhosted/` compose files, Caddy config (auto TLS),
  backup service (`pg_dump` rotation) + restore runbook, upgrade procedure
- Customer docs: install, configure SMTP, licence install, backups, upgrade, troubleshooting
- Operator docs: VPS hardening, firewall egress rules, key ceremony, release process

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
