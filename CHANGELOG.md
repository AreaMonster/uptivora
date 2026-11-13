# Changelog

## 1.0.0 — unreleased

First public release. Release steps: [docs/operations/production-readiness.md](docs/operations/production-readiness.md#go-live-checklist-v10).

### Monitoring
- HTTP(S) checks every 30 s to 24 h with expected status codes, keyword, timeout and
  redirect handling; SSRF protection with DNS-rebinding defence on every request and redirect.
- Outages confirmed by a second check; one email per outage and recovery; SSL expiry warnings
  at 14, 7 and 1 day; flapping protection; up to five extra confirmed recipients with
  one-click unsubscribe.
- Incident history with timeline, acknowledgement and notes; response-time and uptime charts
  for 24 h, 7, 30 and 90 days.
- Alerts are held back while the monitoring server's own network is down (with canary URLs
  configured).

### Editions
- Hosted: Starter / Pro / Business plans with prorated upgrades, downgrades and cancellation
  at period end, past-due grace period; billing in TEST MODE until a payment provider is
  connected.
- Self-hosted: perpetual Ed25519-signed licences verified offline, evaluation mode, team
  invitations, never contacts Uptivora. Licences are signed automatically after payment by an
  isolated signing service and emailed to the customer.

### Administration
- Admin dashboard: overview, users, monitors, plans and pricing, billing and licences,
  system health, logs.
- `python -m app.cli preflight` production checks; `/api/health/service` for external
  monitoring; optional heartbeat URL.

### Operations
- Docker Compose stacks with automatic HTTPS (Caddy), read-only unprivileged containers,
  nightly zstd backups with weekly restore verification, offline release bundle.
- Storage: ~3.5 MB per monitor checked every minute, including two weeks of backups.
- Measured: 10,000 monitors at 60 s on 2 vCPU.

### Legal
- Legal notice, privacy policy, terms of service, self-hosted licence agreement and data
  processing agreement, linked at sign-up and checkout.

### Privacy
- No analytics, trackers or third-party scripts; one session cookie after sign-in.
- Personal data export (JSON) and immediate account deletion in Settings; automatic retention
  for every kind of stored data.
