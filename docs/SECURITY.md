# Security: threat model and verification

Design details of the defences are in [ARCHITECTURE.md](ARCHITECTURE.md) §4.3–4.4. This
document lists what we protect, from whom, how, which test proves it, and which risks are
accepted. Reviewed in Phase 9 (2026-11-13).

## Assets

| Asset | Why it matters |
| --- | --- |
| Licence signing private key | Anyone holding it can mint unlimited lifetime licences |
| Accounts and sessions | Takeover exposes monitors, recipients, billing; admin takeover exposes everyone |
| The monitoring server's network position | Can reach networks that customers' URLs must not reach (SSRF) |
| Alert delivery | Silent failure means missed outages; abuse means spam from our domain |
| Customer data | Email addresses, URLs (may reveal internal naming), incident notes |
| Billing state | TEST payments must never look real; plan limits must hold |

## Actors

1. Anonymous internet user (sign-up form, login, public pages, unsubscribe links)
2. Registered customer — malicious or compromised (controls monitor URLs and recipients)
3. A website being monitored — controls responses, redirects and DNS for its domain
4. Self-hosted customer — full control of their own server, may try to bypass licence limits
5. Network attacker between users and the server
6. Insider / compromised operator machine

## Trust boundaries

Browser ⇄ Caddy (TLS) ⇄ web / API · API and worker ⇄ PostgreSQL (internal network, no
egress) · worker ⇄ internet (monitored sites, SMTP) · operator laptop (licence key, offline).

## Threats and mitigations

| # | Threat | Mitigation | Verified by |
| --- | --- | --- | --- |
| T1 | SSRF: monitor URL points at internal services, cloud metadata or localhost | URL policy (schemes, ports, hostnames, numeric host tricks); every resolved address must be public; connect only to the validated IP | `test_netguard.py` (60+ cases), `test_api_monitors::test_ssrf_targets_rejected` |
| T2 | SSRF via redirect or DNS rebinding | Each redirect target re-validated; resolver result pinned per connection; mixed public/private answers refused | `test_engine_checker.py` redirect, rebinding, mixed-answer tests |
| T3 | SSRF via environment proxies | `trust_env=False`, no proxy mounts | `test_security_hardening::test_monitor_clients_ignore_proxy_environment` |
| T4 | Monitored site sends a huge or slow body | Body read only for keyword checks, capped at 1 MiB; strict timeouts; per-host concurrency 2 | `checker.MAX_BODY_BYTES`, `test_timeout_is_enforced` |
| T5 | Credential stuffing / brute force | Argon2id; per-IP and per-account rate limits on login, registration, reset; uniform errors | `test_api_auth::test_rate_limit`, `test_login_errors_are_uniform`, `test_forgot_password_is_rate_limited_per_address` |
| T6 | Session theft or fixation | Random 256-bit token, only SHA-256 stored; HttpOnly, SameSite=Lax, `__Host-` + Secure on HTTPS; new token on login; idle (7 d) and absolute (30 d) expiry; server-side revocation | `test_security_hardening` session tests, `test_api_account::test_change_password_revokes_other_sessions` |
| T7 | CSRF | Per-session token header on every mutation, bound to its session; Origin / Sec-Fetch-Site check on all unsafe requests | `test_csrf_required_for_mutations`, `test_cross_site_requests_blocked`, `test_csrf_token_is_bound_to_its_session` |
| T8 | IDOR: reading or changing another customer's data | Every query scoped by owner; admin routes require role and CSRF | `*_are_private` / `*_invisible` tests, `test_admin.py` RBAC sweep over all `/api/admin` routes |
| T9 | Mass assignment (role, verification, owner) | Explicit Pydantic input models; unknown fields ignored | `test_registration_ignores_privileged_fields`, `test_profile_update_cannot_change_role_or_email` |
| T10 | Spoofed client IP to dodge rate limits | `X-Forwarded-For` honoured only from `UPTIVORA_TRUSTED_PROXIES` (Caddy's subnet), right-most untrusted hop | `test_client_ip_only_trusts_configured_proxies` |
| T11 | XSS | React escaping, no `dangerouslySetInnerHTML` with user data; CSP without external sources; API answers only JSON with `default-src 'none'` | ZAP baseline, CSP console check, `test_templates_escape_and_stay_self_contained` |
| T12 | Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` | `test_security_headers`, ZAP baseline |
| T13 | Using Uptivora to spam third parties | Extra recipients must confirm by link first; one-click unsubscribe (HMAC-signed); test-alert and contact rate limits | `test_notifications.py` |
| T14 | Email header injection | Subjects flattened to one line; only allow-listed extra headers, dropped if they contain CR/LF; invalid recipients raise | `test_security_hardening::test_email_headers_cannot_be_injected` |
| T15 | Forged or edited licence | Ed25519 signature over canonical payload; dev key only trusted in development/test, which refuse public URLs | `test_licensing.py`; production image rejects dev-signed licence (Phase 8 stack test) |
| T16 | Leak of the signing key | Key never on servers or in images; offline generation; passphrase-encrypted; release script refuses tracked key files | `LICENSE_KEY_OPERATIONS.md`, `deploy/release/build.sh` |
| T17 | Self-hosted install phones home / leaks data | No outbound calls except checks and SMTP | `test_no_phone_home.py` (static + runtime connection spy) |
| T18 | Container breakout impact | Non-root, read-only FS, `cap_drop: ALL`, `no-new-privileges`, DB on internal network | `deploy/*/compose.yaml`, image check in release script |
| T19 | TEST payments mistaken for real revenue | Test provider refused in production unless explicitly allowed; TEST labels in UI, emails, MRR split | `test_billing.py`, `test_config.py` |
| T20 | Vulnerable dependencies | Pinned versions; audits each release | see results below |
| T21 | Leaked secrets in the repository | `.gitignore` for keys/secrets/.env; release script refuses tracked key files; gitleaks over the full history | gitleaks: no leaks (Phase 10) |
| T22 | Our own outage emails every customer (alert storm) | Canary-confirmed local network detection holds alerts; off without canaries so real outages are never suppressed | `test_monitoring_the_monitor.py` |
| T23 | Silent death of the service | Public `/api/health/service` for external checks; optional outbound heartbeat; preflight command | `test_monitoring_the_monitor.py`, `test_preflight.py` |

## Accepted risks

- **`script-src 'unsafe-inline'`.** Next.js streams page data in inline scripts; nonces would
  force every page to render per request. External script sources stay blocked and all
  user content is escaped by React. Revisit if Next.js gains hash-based CSP for static pages.
- **Per-account login limit can lock out a victim** for up to 15 minutes if someone guesses
  their email and sends 10 wrong passwords. Preferred over unlimited guessing.
- **Registration reveals whether an email has an account** (409 on duplicate). Password reset
  does not. Hiding it on sign-up would require email-first registration.
- **Self-hosted licence enforcement is client-side by nature.** A customer controlling the
  server can patch the code. The licence deters casual copying; it is not DRM.
- **Offline verification cannot revoke** a leaked key in installations that never upgrade.

## Phase 9 results (2026-11-13)

| Check | Result |
| --- | --- |
| Backend tests | 299 passed: 19 new hardening tests found no security defects; 3 further tests cover the Phase 9 performance fixes |
| `pip-audit` (runtime dependencies, `backend/constraints.txt`) | No known vulnerabilities |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `npm audit` incl. dev tools | 7 moderate (minimatch ReDoS in typescript-eslint) → fixed with an `overrides` pin; now 0 |
| `ruff` security rules (S) | Clean |
| `bandit -r app` | 7 low/medium findings, all reviewed false positives (constant table names, jitter randomness, enum labels); one `assert` replaced by an explicit error |
| `semgrep` OSS (python, typescript, react, nextjs, secrets, docker rules) | 1 finding, the same constant-table-name false positive, annotated |
| OWASP ZAP baseline (production images behind Caddy) | 0 failures, 63 passed, 5 warnings: CSP `unsafe-inline` (accepted), missing COEP (fixed: COEP `require-corp` + CORP added), three informational cache / robots notices (robots.txt added) |
| CSP in the browser | No violations on the landing, pricing, docs, dashboard, monitor, settings and billing pages |

### How to repeat

```bash
cd backend && .venv/Scripts/python -m pytest -q && .venv/Scripts/python -m ruff check .
.venv/Scripts/python -m pip_audit -r constraints.txt
.venv/Scripts/python -m bandit -q -r app
cd ../frontend && npm audit
docker run --rm -v "$PWD:/src" -w /src semgrep/semgrep semgrep scan --metrics=off \
  --config p/python --config p/typescript --config p/react --config p/nextjs --config p/secrets
# ZAP: start deploy/selfhosted with a dotted host name (Java omits SNI for "localhost")
docker run --rm --add-host uptivora.localhost:host-gateway ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t https://uptivora.localhost:8443/
```

## Reporting a vulnerability

Until the security contact address is set up (Phase 10, before launch), report privately to the operator rather than in a public issue. Include steps to reproduce. Please do not test against other
customers' data or run automated scanners against the hosted service without agreement.
