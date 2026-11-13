# Installing Uptivora

## Requirements

- A 64-bit Linux server. 1 vCPU and 1 GB RAM handle up to ~500 monitors; in our load test
  2 vCPU kept up with 10,000 monitors checked every minute (use 4 GB RAM at that size).
- Disk for the database and two weeks of backups: about 3.5 MB per monitor checked every
  minute (2.5 MB at 5-minute checks), plus 5 GB. Details in the operator documentation
  (`docs/PERFORMANCE.md` in the source repository).
- Docker Engine 24 or newer with the Compose plugin (`docker compose version` must work).
- A DNS name (A and/or AAAA record) pointing at the server, for example `monitor.example.com`.
- Ports 80 and 443 reachable from the internet, so a certificate can be issued. For an
  intranet without public DNS see [Intranet installations](#intranet-installations).
- An SMTP server or relay that may send mail for your domain ([smtp.md](smtp.md)).

Install Docker from your distribution or with Docker's official instructions. Then:

```bash
tar xzf uptivora-selfhosted-<version>.tar.gz
cd uptivora-selfhosted-<version>
./install.sh
```

`install.sh` copies `.env.example` to `.env`, generates a random database password and secret
key in `secrets/` and loads the Uptivora images from `images/`. It never overwrites existing
files, so it is safe to run again.

## Configure

Edit `.env`. The required values are at the top:

| Setting | Meaning |
| --- | --- |
| `UPTIVORA_DOMAIN` | Host name users open, without `https://` |
| `UPTIVORA_SMTP_HOST`, `_PORT`, `_SECURITY`, `_USERNAME` | Outgoing mail server ([smtp.md](smtp.md)) |
| `UPTIVORA_SMTP_FROM` | Sender of alert emails, e.g. `Uptivora <monitoring@example.com>` |

Put the SMTP password into `secrets/smtp_password` (one line, no quotes).

Optional settings:

| Setting | Default | Meaning |
| --- | --- | --- |
| `UPTIVORA_TLS` | `auto` | `auto`: public certificate. `internal`: Caddy's own CA |
| `UPTIVORA_HTTP_PORT`, `UPTIVORA_HTTPS_PORT` | `80`, `443` | Published ports |
| `UPTIVORA_PUBLIC_URL` | `https://<domain>` | Set only when users use a non-standard port |
| `BACKUP_TIME`, `BACKUP_KEEP_DAYS` | `02:30`, `14` | Nightly backup schedule ([backups.md](backups.md)) |
| `TZ` | `Europe/Zurich` | Time zone of the backup schedule and log timestamps |
| `UPTIVORA_WORKER_CONCURRENCY` | `50` | Checks that may run at the same time |
| `UPTIVORA_RAW_RETENTION_DAYS` | `3` | How long every individual check is kept (charts beyond 24 hours use hourly summaries, kept 400 days) |
| `UPTIVORA_FAILED_CHECK_RETENTION_DAYS` | `30` | How long failed checks and the checks around incidents are kept |
| `BACKUP_VERIFY_WEEKDAY` | `7` | Day (1 = Monday … 7 = Sunday, 0 = never) the new backup is test-restored |
| `UPTIVORA_HEARTBEAT_URL` | empty | Requested every minute while checks run, e.g. a healthchecks.io URL — another service then alerts you if this server stops |
| `UPTIVORA_NETWORK_CANARIES` | `[]` | Public URLs that tell a network outage of this server apart from real outages ([troubleshooting.md](troubleshooting.md#alerts-are-held-back)). Off by default |
| `UPTIVORA_SUBNET` | `10.250.47.0/24` | Internal Docker network; change it only if it overlaps your LAN |

## Start

```bash
docker compose up -d
docker compose ps
```

All services should be `running` (`migrate` exits after applying database migrations).
Check the configuration:

```bash
docker compose run --rm api python -m app.cli preflight --smtp
```

Open `https://<your domain>`, create the first account — it becomes the administrator — and
follow the setup checklist on the admin overview: install the licence, send a test email,
add your first monitor, invite colleagues.

## What runs where

| Service | Purpose | Network access |
| --- | --- | --- |
| `caddy` | HTTPS on ports 80/443, certificates | internet (certificate authority) |
| `web` | the web interface | internal only |
| `api` | the application server | internal; DNS for validating monitor URLs |
| `worker` | runs the checks, sends email, nightly housekeeping | the websites you monitor, your SMTP server |
| `db` | PostgreSQL 17 | none — on an internal network without outside access |
| `backup` | nightly `pg_dump` into `./backups` | database only |
| `migrate` | applies database migrations at start, then exits | database only |

Every Uptivora container runs as an unprivileged user with a read-only file system and no
Linux capabilities. The database is not published on any port.

**Outbound connections.** Uptivora only connects to the websites you monitor, your SMTP
server and DNS. Caddy additionally talks to Let's Encrypt or ZeroSSL to obtain certificates
when `UPTIVORA_TLS=auto`. Nothing contacts Uptivora. If your firewall restricts outbound
traffic, allow TCP 80/443 for checks, your SMTP port, and DNS.

## Intranet installations

Without public DNS, Caddy cannot get a public certificate. Set `UPTIVORA_TLS=internal`: Caddy
then signs its own certificate. Browsers warn until you trust Caddy's root certificate, which
you can export with:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./uptivora-root.crt
```

Distribute it to your users' trust stores (e.g. by group policy).

Monitored websites must still be public: Uptivora refuses private addresses (10.x, 192.168.x,
localhost …) to prevent abuse of the server as a network scanner.

## Behind an existing reverse proxy

If another proxy already terminates TLS, publish Caddy on other ports
(`UPTIVORA_HTTP_PORT=8080`, `UPTIVORA_HTTPS_PORT=8443`, `UPTIVORA_TLS=internal`) and point the
proxy at `https://<server>:8443`, keeping the original `Host` header. Rate limits then see the
proxy's address for every user; this is safe but means limits are shared.

## Uninstall

```bash
docker compose down        # stops everything, keeps data
docker compose down -v     # also deletes the database and certificates — irreversible
```
