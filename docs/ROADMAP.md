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

## Phase 2 — Authentication, frontend shell, customer dashboard

Backend
- Auth API: register, login, logout, `/me`, email verification, password reset, session list
  and revoke; server-side sessions; CSRF header + Origin check; Postgres rate limiter
- `LimitsProvider` (hosted: plan; self-hosted: licence) and monitor CRUD API with limit
  enforcement and SSRF validation
- Notification preferences API
- Error format, request IDs, structured JSON logging

Frontend (Next.js App Router, TypeScript, Tailwind, Recharts)
- Design system: tokens, typography (Inter, self-hosted), buttons, inputs, cards, status pills
- Public homepage, pricing (reads plans from API), self-hosted page, docs skeleton
- Login / register / forgot / reset pages
- Dashboard: monitor list with status, response time, 24 h uptime; add/edit/delete monitor;
  monitor detail page (charts fed by API); account settings

Tests: API tests (pytest + httpx ASGI), auth security tests (CSRF, enumeration, lockout),
Playwright smoke test for register → add monitor.

## Phase 3 — Monitoring engine and background jobs

- `GuardedNetworkBackend` (httpcore) — dial only validated IPs, SNI/Host preserved
- Check executor: timeouts (connect/read/total), manual redirect handling with re-validation,
  status-range and optional keyword matching, body cap, TLS certificate capture
- Scheduler loop with `FOR UPDATE SKIP LOCKED` leases, jitter, concurrency semaphore,
  per-host concurrency cap, graceful shutdown, crash recovery via lease expiry
- Incident state machine (thresholds, confirmation re-check, single open incident)
- Housekeeping loops (advisory-locked): hourly rollups, retention, SSL sweep, heartbeats
- Tests: local test HTTP servers (up/down/slow/redirect-to-private/rebinding DNS stub),
  state machine property tests, load test with 2 000 simulated monitors

## Phase 4 — Email notifications and incident management

- SMTP sender (aiosmtplib) with STARTTLS/TLS, outbox loop with back-off, dead-letter state
- Templates (plain text + simple HTML): down, recovery, SSL expiring/error, verify email,
  password reset, account changes; per-user preferences, per-monitor mute
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
