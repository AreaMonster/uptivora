# Uptivora — Architecture

Status: Phases 1–3 implemented (2026-11-12). This document is the source of truth for how the
system is put together. Changes to it should be deliberate.

## 1. Guiding constraints

| Constraint | Consequence in the design |
|---|---|
| No paid APIs, no runtime AI | Every dependency is open source and self-hostable. SMTP for email, Let's Encrypt via Caddy for TLS, Ed25519 via `cryptography` for licences. |
| Runs on a small VPS (2 vCPU / 2–4 GB) | 4 processes total (proxy, web, api, worker) + PostgreSQL. No Redis, no message broker, no Elasticsearch. |
| Self-hosted must work offline, forever | Licence verified locally with an embedded public key. No phone-home, no telemetry, no activation server. |
| One codebase, two editions | `UPTIVORA_EDITION=hosted|selfhosted` toggles billing/licensing modules. Monitoring engine is byte-identical in both. |
| Security first | SSRF guard at the socket layer, Argon2id passwords, server-side sessions, CSRF tokens, strict headers, RBAC. |

## 2. Runtime topology

```
                 Internet
                    │ 443 (TLS, Let's Encrypt via Caddy — free)
              ┌─────▼─────┐
              │   Caddy   │  reverse proxy, TLS, security headers, gzip
              └──┬─────┬──┘
     /api/*      │     │   everything else
          ┌──────▼─┐ ┌─▼────────┐
          │  api   │ │   web    │  Next.js (SSR + static), TypeScript, Tailwind
          │FastAPI │ └──────────┘
          └───┬────┘
              │ SQL (asyncpg)
       ┌──────▼───────┐        ┌──────────────┐
       │  PostgreSQL  │◄───────┤   worker     │  async monitoring engine
       │  (only state)│  SQL   │ (1..N procs) │  + housekeeping + mail outbox
       └──────────────┘        └──────┬───────┘
                                      │ outbound HTTP(S) via SSRF-guarded client
                                      │ outbound SMTP (customer-configured)
                                      ▼
                            customer websites / SMTP server
```

* **Same origin.** Browser only talks to Caddy. `/api/*` is proxied to FastAPI, the rest
  to Next.js. One origin means cookies are `SameSite=Lax`, no CORS surface.
* **PostgreSQL is the only stateful service.** Sessions, rate-limit counters, job queue
  (monitor scheduling), mail outbox and worker heartbeats all live in Postgres.
  This is a conscious choice to avoid Redis (see §7 Risk R6 for the trade-off).
* **The worker is a separate process** from the API so a slow website or SMTP outage
  never affects dashboard latency, and so it can be scaled to N processes or moved to a
  second VPS without code changes.

## 3. Backend modules (`backend/app`)

```
app/
  core/          config, db engine/session, security primitives, logging, errors
    config.py        pydantic-settings; reads env vars + *_FILE secrets
    db.py            async engine, session factory
    security.py      Argon2id hashing, token generation, constant-time compare
    netguard.py      SSRF: URL validation, IP classification, guarded DNS+connect
  models/        SQLAlchemy 2.0 ORM models (single schema for both editions)
  licensing/     Ed25519 licence format, verification, embedded public keys
  auth/          registration, login, sessions, CSRF, password reset   (Phase 2)
  monitors/      CRUD, plan/licence limit enforcement                  (Phase 2/3)
  engine/        check executor, scheduler loop, incident state machine (Phase 3)
  notifications/ outbox, SMTP sender, templates, preferences            (Phase 4)
  admin/         admin API: stats, users, plans, logs, health           (Phase 5)
  billing/       plans, subscriptions, payment provider interface,
                 TEST MODE simulator; Stripe adapter later (disabled)   (Phase 6)
  selfhosted/    first-run setup, licence install, edition limits       (Phase 7)
  api/           FastAPI routers wiring the modules above
  main.py        API process entry point
  worker.py      worker process entry point
tools/licensegen/  OFFLINE licence generator — never shipped in images
```

Dependency direction: `api → (auth|monitors|billing|admin|selfhosted) → (engine|licensing|notifications) → core/models`.
`engine` never imports `billing`; it only asks a `LimitsProvider` for limits, which is
implemented by `billing` (hosted) or `licensing` (self-hosted). That is how the engine stays
identical across editions.

## 4. Key design decisions

### 4.1 Scheduling: Postgres as the job queue (instead of APScheduler + Redis)

Each monitor row carries `next_check_at`. Worker loop:

```sql
UPDATE monitors SET lease_until = now() + interval '60 s', lease_owner = :worker
WHERE id IN (
  SELECT id FROM monitors
  WHERE is_paused = false AND next_check_at <= now()
    AND (lease_until IS NULL OR lease_until < now())
  ORDER BY next_check_at
  LIMIT :batch
  FOR UPDATE SKIP LOCKED)
RETURNING ...;
```

Checks run concurrently under an `asyncio.Semaphore`. After each check the worker writes the
result, updates monitor state and sets `next_check_at = scheduled + interval` (with jitter).

Why not APScheduler: an in-memory scheduler must be rebuilt from the DB on every change,
loses state on crash, and cannot be safely run as multiple processes. The SKIP LOCKED pattern
gives crash recovery (lease expiry), horizontal scaling and exactly-one-worker-per-check with
zero extra infrastructure. Periodic housekeeping (rollups, retention, SSL sweep,
subscription renewals, outbox) runs as simple timed loops inside the worker, each guarded by a
Postgres advisory lock so that only one worker performs it.

### 4.2 Incident state machine (no flapping, no duplicate alerts)

```
           fail (count < down_threshold)              success
   UP ─────────────────────────────► UP*  ───────────────────────► UP
    │ fail (count ≥ down_threshold)
    ▼
  DOWN  ── open incident, enqueue "down" notification (dedupe_key = incident:<id>:down)
    │ success (count ≥ recovery_threshold)
    ▼
   UP   ── close incident, enqueue "recovery" notification (dedupe_key = incident:<id>:up)
```

* Default `down_threshold = 2` consecutive failures (confirmation re-check after 30 s rather
  than waiting a full interval), `recovery_threshold = 1`.
* Notifications go through `notification_outbox` with a **unique `dedupe_key`**. A crash and
  retry can never send the same alert twice, because the insert simply conflicts.
* At most one open incident per monitor (partial unique index on `incidents(monitor_id) WHERE resolved_at IS NULL`).

### 4.3 SSRF defence in depth

1. **At input time** (`netguard.validate_monitor_url`): scheme ∈ {http, https}; no userinfo;
   port in allowlist (80, 443, 1024–65535 except known-internal ports); hostname not an IP
   literal in a blocked range, not `localhost`, not single-label, not `*.internal`, `*.local`,
   etc.; IDNA-normalised; length limits.
2. **At connect time** (`netguard.GuardedNetworkBackend`): a custom `httpcore` network backend
   resolves DNS itself, rejects the connection if **any** resolved address is non-global
   (RFC1918, loopback, link-local incl. 169.254.169.254 metadata, CGNAT, ULA, multicast,
   reserved, IPv4-mapped/6to4/Teredo/NAT64 wrapping a private v4), and then connects to the
   **already-validated IP**. Host header and TLS SNI/certificate validation still use the
   hostname. Because the address that was checked is the address that is dialled, DNS
   rebinding (TOCTOU) is not possible.
3. **Redirects** are never followed automatically. The engine follows up to 5 hops manually,
   re-running step 1 on each `Location`, refusing https→http downgrades, and step 2 applies
   automatically on every connection.
4. **Response handling**: body read is capped (default 64 KiB, only needed for keyword checks),
   total time capped by an overall deadline, `trust_env=False` (ignores proxy env vars).
5. **Egress firewall (deployment)**: the docker-compose worker network can only reach the
   internet; documented `iptables`/`nftables` rules block RFC1918 egress from the worker as a
   last line of defence.

### 4.4 Authentication & sessions

* Argon2id (`argon2-cffi`, RFC 9106 low-memory profile) with transparent rehash on login.
* Server-side sessions: random 256-bit token in an `HttpOnly; Secure; SameSite=Lax` cookie;
  only `SHA-256(token)` stored in `sessions`. Idle timeout 7 days, absolute 30 days,
  revocable from account settings and by admins.
* CSRF: per-session random token returned by `/api/auth/me`, required in an
  `X-CSRF-Token` header on every unsafe method; verified with constant-time compare. Plus
  `Origin` header check. (SameSite=Lax alone is not relied upon.)
* RBAC: `role ∈ {user, admin}`; admin routes depend on `require_admin`. Every resource query
  is scoped `WHERE owner_id = current_user.id` in the repository layer, never in the router.
* Rate limits (Postgres fixed-window counters): login 10/min/IP and 5/min/email, register
  5/hour/IP, password reset 3/hour/email, generic API 300/min/user.

### 4.5 Data retention & uptime history

`check_results` is the high-volume table (50 monitors × 1/min ≈ 72k rows/day per Business
customer). Strategy:

* Raw results kept 30 days (configurable), deleted daily in batches.
* Hourly rollups (`check_rollups`: total, up, avg/min/max/p95 latency) kept 400 days.
* Uptime % for 24 h uses raw data; 7/30/90-day charts read rollups. Incidents are kept forever.
* Native partitioning is deliberately postponed (risk R4) — batch deletes on an index of
  `(checked_at)` are sufficient below ~50M rows.

### 4.6 Email

`aiosmtplib` against any SMTP server (customer's own, Postfix, Mailcow, Gmail SMTP, etc.).
Messages are written to `notification_outbox` inside the same DB transaction as the state
change that caused them; the worker's outbox loop sends with exponential back-off
(1 min → 6 h, 10 attempts). Dev uses Mailpit (open source) to capture mail.

### 4.7 Billing (hosted only)

`PaymentProvider` interface (`create_checkout`, `cancel`, `handle_webhook`). Implementations:

* `TestModeProvider` — enabled only when `BILLING_PROVIDER=test`. Every payment row is stored
  with `is_test = true`, the UI shows a persistent **TEST MODE — no real money is charged**
  banner, and receipts/emails are prefixed `[TEST]`. Refuses to start if `ENV=production`
  unless `ALLOW_TEST_BILLING_IN_PRODUCTION=true` is explicitly set (for staging).
* `StripeProvider` — stub, disabled. When enabled it must verify webhook signatures
  (`Stripe-Signature`, HMAC-SHA256, 5-minute tolerance) and use idempotency keys. No Stripe
  call is ever made in test mode.

Subscriptions are stored locally; renewals are handled by a worker loop that moves
`active → past_due → expired` when `current_period_end` passes without a successful payment.
Downgrades take effect at period end; if the user then has more monitors than allowed, the
excess monitors are **paused, never deleted**.

## 5. Frontend (`frontend/`)

Next.js (App Router) + TypeScript + Tailwind + Recharts (MIT). Route groups:

```
(marketing)/  /, /pricing, /self-hosted, /docs/**     static, SEO
(auth)/       /login, /register, /forgot-password, /reset-password
(app)/        /dashboard, /monitors/[id], /incidents, /settings/**, /billing
(admin)/      /admin, /admin/users, /admin/plans, /admin/monitors, /admin/system,
              /admin/logs, /admin/licences
```

The browser calls the API through the same origin. Server components call the API over the
internal Docker network, forwarding the session cookie. No secrets are ever sent to the
browser bundle. Design tokens: navy `#0B1220`, charcoal `#151B26`, surface `#1C2433`,
emerald `#10B981` (up), turquoise `#14B8A6` (accent), amber `#F59E0B` (degraded/SSL),
rose `#F43F5E` (down). Typeface: Inter (self-hosted via `next/font`, no Google calls at runtime).

## 6. Deployment

`deploy/docker-compose.yml` (hosted) and `deploy/selfhosted/docker-compose.yml`
(self-hosted bundle) share the same images. Services: `caddy`, `web`, `api`, `worker`,
`db` (postgres:17-alpine), `backup` (pg_dump cron, rotated, optional off-site via rsync).
Secrets via Docker secrets / `*_FILE` env vars. Database migrations run as a one-shot
`api migrate` step before the API starts.

## 7. Technical risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **SSRF / internal network access** through customer URLs | Critical — cloud metadata theft, internal scanning | Socket-layer guard (§4.3), redirect re-validation, egress firewall, dedicated tests incl. rebinding. |
| R2 | **Licence piracy** — an offline licence cannot be revoked and the check can be patched out of the source | Revenue loss | Accept it: offline + source-available means a determined user can always bypass. Make the honest path easy, put licensee name visibly in the UI, sell updates/support. Do not add DRM that hurts paying customers. |
| R3 | **Private signing key compromise** | Anyone can mint licences | Key lives only offline (encrypted PKCS#8, passphrase). `key_id` in every licence + list of trusted public keys allows rotation; documented incident procedure. |
| R4 | `check_results` growth | Disk, slow queries | Hourly rollups + retention job; partitioning as a later upgrade path. |
| R5 | **False positives / alert noise** from one vantage point | Customer churn | Confirmation re-check, thresholds, timeouts tuned; multi-location checks are a roadmap item (a second cheap VPS running another worker). |
| R6 | No Redis → rate limits and scheduling hit Postgres | Load at scale | Fine to ~10–20k monitors on one box. Interfaces are abstracted so Redis can be added later if needed. |
| R7 | **Outbound IP reputation / abuse** — customers use the monitor to hammer third parties | Hosting provider complaints | Minimum interval per plan (≥ 30 s), per-host concurrency cap, identifiable User-Agent with a contact URL, admin can suspend monitors. |
| R8 | **SMTP deliverability** without a paid email API | Alerts land in spam | Docs for SPF/DKIM/DMARC; support any SMTP relay; outbox retries. |
| R9 | Swiss/EU legal: VAT, consumer law, GDPR/revDSG, payment provider ToS | Compliance | Real billing stays disabled until a provider account exists; data stays on our VPS; no tracking; DPA + privacy policy templates are a Phase 10 item (needs a lawyer, not code). |
| R10 | **Clock skew** across workers | Wrong uptime numbers | All timestamps from Postgres `now()` / UTC, NTP required in docs. |
| R11 | Project folder is inside OneDrive | `node_modules`/`.venv` sync storms, file locks | Exclude those folders from OneDrive or move the repo outside it. |
