# Database Schema

PostgreSQL 15+ (developed on 17). Source of truth: `backend/app/models/`, migrations in
`backend/alembic/versions/`. All timestamps are `timestamptz` in UTC. Enum-like columns are
`varchar` + `CHECK` constraints (cheap to extend, unlike native PG enums).

## Tables

| Area | Table | Purpose / key invariants |
|---|---|---|
| Identity | `users` | email unique and forced lowercase (`CHECK`); Argon2id hash; `role` user/admin |
| | `sessions` | server-side sessions; only SHA-256 of the cookie token stored; CSRF token; absolute expiry |
| | `auth_tokens` | single-use email tokens (verify, reset, invite), hashed |
| Monitoring | `monitors` | config + live state + worker lease; `interval_seconds >= 30` (`CHECK`); partial index on due, unpaused monitors |
| | `check_results` | one row per check (bigint identity); `(monitor_id, checked_at DESC)` index; retained N days |
| | `check_rollups` | hourly aggregates, PK `(monitor_id, bucket_start)`; long-term charts |
| | `incidents` | outage periods, acknowledgement and note; **partial unique index: one open incident per monitor** |
| Notifications | `notification_settings` | per-user preferences (down / recovery / SSL, warning days, send to account email) |
| | `alert_contacts` | extra alert recipients; receive alerts only once `verified_at` is set; unique per user |
| | `notification_outbox` | transactional outbox; **unique `dedupe_key` prevents duplicate alerts**; retry/back-off fields |
| Billing (hosted) | `plans` | editable catalogue (seeded Starter/Pro/Business CHF 5/12/25) |
| | `subscriptions` | **partial unique index: one live (active/past_due/cancelled) subscription per user**; scheduled downgrade via `pending_plan_id`; `simulate_failure` (TEST MODE only) and `last_payment_attempt_at` for retries |
| | `payments` | every row has `is_test`; unique `(provider, provider_payment_id)` for idempotency |
| | `license_products` | self-hosted products (seeded CHF 99 / 199), signed limits template |
| | `license_orders` | purchase → offline signing → signed licence text attached |
| | `webhook_events` | unique `(provider, event_id)`: each provider event processed once |
| System | `installed_licenses` | self-hosted: installed licence text, re-verified on every load; one active |
| | `worker_heartbeats` | worker liveness and counters for the admin dashboard |
| | `audit_log` | security-relevant actions |
| | `system_events` | operational log shown in admin |
| | `app_settings` | admin-editable non-secret settings |
| | `rate_limit_buckets` | **UNLOGGED** fixed-window counters |

## Deletion semantics

* Deleting a user cascades to their sessions, tokens, monitors (→ results, rollups, incidents),
  preferences and subscriptions. Payments and licence orders keep their row with `user_id = NULL`
  (financial records).
* Plans and licence products cannot be deleted while referenced (`RESTRICT`); deactivate them instead.

## Common commands

```bash
cd backend
.venv/Scripts/alembic upgrade head          # apply migrations
.venv/Scripts/alembic revision --autogenerate -m "describe change"
.venv/Scripts/alembic check                 # fails if models and migrations drift
```
