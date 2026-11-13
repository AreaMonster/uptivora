# Incident runbooks

Start every incident the same way:

```bash
docker compose ps
curl -s https://<domain>/api/health/service       # {"status","checks","email"}
docker compose logs --since 30m worker api | tail -200
```

Admin → System shows workers, overdue monitors, the email queue and disk; Admin → Logs the
recent warnings. Keep a short timeline (what you saw, what you did, when) for the follow-up.

## Checks stopped — `"checks": "stopped"` or `"delayed"`

1. `docker compose ps worker` — not running? `docker compose up -d worker`, then
   `docker compose logs worker`.
2. Running but no heartbeat: database reachable? (`docker compose exec db pg_isready`)
3. `"delayed"` with a live worker: overdue monitors pile up faster than they are checked.
   Admin → System shows how many. Raise `UPTIVORA_WORKERS` (hosted) or
   `UPTIVORA_WORKER_CONCURRENCY`, and check CPU (`docker stats`).
4. After recovery overdue checks run immediately; nothing else to do.

## Alerts held — `"checks": "held"`

The worker saw most sites *and* all canary URLs fail with network errors: this server's own
connectivity or DNS is down. Outage emails are held back and checks retried every minute;
nothing is lost.

1. From the server: `docker compose exec worker python -c "import socket; print(socket.getaddrinfo('example.com', 443)[0][4])"`
   and `curl -sI https://www.wikipedia.org`.
2. Fix DNS / routing / firewall egress, or contact the hosting provider.
3. If the canary sites themselves are down (rare), set other ones in
   `UPTIVORA_NETWORK_CANARIES` and `docker compose up -d worker`.

## Email delayed — `"email": "delayed"`

1. Admin → Logs: the SMTP server's error for each failed attempt.
2. `docker compose run --rm api python -m app.cli preflight --smtp` tests the login.
3. Typical causes: expired SMTP password, provider sending limit, sender address not allowed.
   Queued alerts are retried automatically for several hours once SMTP works again.

## Disk almost full

1. `df -h`, `du -sh backups`, Admin → System → largest tables.
2. Copy backups off the server, then lower `BACKUP_KEEP_DAYS`.
3. Database too large: lower `UPTIVORA_RAW_RETENTION_DAYS` (default 3) — partitions older than
   that are dropped at the next retention run (every 6 h, or restart the worker).
4. Never delete files inside the PostgreSQL volume by hand.

## Database down or damaged

1. `docker compose logs db`. Disk full → see above. Permission errors after a host change →
   restore into a fresh volume.
2. Restore: [../selfhosted/backups.md](../selfhosted/backups.md#restore). Data since the last
   dump is lost; monitors simply resume checking.

## Certificate not renewed

`docker compose logs caddy` — DNS no longer points here, or port 80/443 blocked. Caddy retries
on its own once fixed. The site keeps the old certificate until it expires (renewal starts
30 days before).

## A customer says an alert never came

1. Their monitor → Incidents: was an incident opened? If not, the site answered the checks
   (check the recent checks list) or the monitor was paused.
2. Their Settings → Recipients → Recent alert emails: sent, failed, or not created?
3. Sent: deliverability (spam folder, SPF/DKIM of the sending domain).
4. Held because of a local network problem at that time? Admin → Logs.

## Suspected security incident

1. Preserve evidence first: `docker compose logs > incident-<date>.log`, a database dump.
2. Compromised admin account: suspend it (Admin → Users), revoke its sessions, rotate
   passwords.
3. Leaked `secrets/secret_key`: replace it (`openssl rand -base64 48`), `docker compose up -d` —
   all sessions end and old unsubscribe links stop working.
4. Leaked licence **signing** key: [../LICENSE_KEY_OPERATIONS.md](../LICENSE_KEY_OPERATIONS.md#compromise).
5. Personal data affected: check the notification duties in the legal handover
   ([legal-handover.md](legal-handover.md)) — under the revDSG/GDPR the clock starts when you
   become aware of the breach.

## Bad release

Roll back as in [../selfhosted/upgrade.md](../selfhosted/upgrade.md#rolling-back): restore the
dump taken before the upgrade, set the previous `UPTIVORA_VERSION`, `docker compose up -d`.
