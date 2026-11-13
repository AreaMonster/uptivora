# Hosted deployment (operator runbook)

The hosted service runs the same images as the self-hosted bundle with
`deploy/hosted/compose.yaml`. Read [vps-hardening.md](vps-hardening.md) and
[firewall.md](firewall.md) first.

## Sizing

Measured in Phase 9 ([../PERFORMANCE.md](../PERFORMANCE.md)): one worker process keeps up with
10,000 monitors at 60 s using under half a CPU core; PostgreSQL adds about a quarter core.
Storage: ~3.5 MB per monitor at 60 s including 14 backups, after 400 days.

| Load | Server |
| --- | --- |
| up to ~2,000 monitors at 60 s | 2 vCPU, 4 GB RAM, 40 GB SSD |
| up to ~10,000 monitors at 60 s | 2–4 vCPU, 8 GB RAM, 80 GB SSD |

## First deployment

```bash
sudo mkdir -p /opt/uptivora && sudo chown deploy: /opt/uptivora
git clone <repo> /opt/uptivora/src            # or copy the deploy/ directory of a release
cd /opt/uptivora/src/deploy/hosted
sh init.sh                                    # .env + secrets/
nano .env                                     # domain, SMTP, capacity
nano secrets/smtp_password
docker load -i uptivora-<version>.tar.gz      # images from the release build (release.md)
docker compose up -d
docker compose ps
```

Create the operator account (the first account in the hosted edition is an ordinary user):

```bash
docker compose run --rm api python -m app.cli create-user --email ops@uptivora.com --admin
```

The command prompts for the password. Then sign in and check Admin → System.

## Licence signing

The `signer` service signs self-hosted licences automatically after payment. It needs the
shop key once — setup, rotation and incident steps in
[../LICENSE_KEY_OPERATIONS.md](../LICENSE_KEY_OPERATIONS.md). Without a key it reports
`no_key` and paid orders wait in Admin → Billing & licences for a manually signed file.

## Billing

`UPTIVORA_BILLING_PROVIDER=disabled` (default) hides upgrades; plans can be assigned by an
administrator. `test` simulates payments and is labelled TEST MODE everywhere; the API refuses
it in production unless `UPTIVORA_ALLOW_TEST_BILLING_IN_PRODUCTION=true` — set that only on a
staging system that has its own domain. Real payment collection stays disabled until a payment
provider account, terms and VAT handling exist (Phase 10).

## Backups

The `backup` service writes a dump every night to `BACKUP_DIR`. Copy it off the server daily
(object storage with versioning, or a pull from a backup host):

```bash
# on the backup host
rsync -a app.uptivora.com:/opt/uptivora/src/deploy/hosted/backups/ /srv/backups/uptivora/
```

Once a month, restore the latest dump on a scratch machine with `uptivora-backup verify` and
record the result. Procedure and restore steps: [../selfhosted/backups.md](../selfhosted/backups.md).

## Updates

Same procedure as [../selfhosted/upgrade.md](../selfhosted/upgrade.md): backup, load the new
images, set `UPTIVORA_VERSION`, `docker compose up -d`. The old API keeps running until
`migrate` has finished, so write migrations that the previous release can live with for a
few seconds: add columns as nullable or with a default, drop columns one release later.

## Monitoring the monitor

Uptivora cannot alert about its own outage. Set up at least one of these, alerting you through
a channel that does not depend on this server:

- An external uptime check of `https://app.uptivora.com/api/health/service`: 200 while checks
  run and email flows, 503 with `"checks": "stopped" | "delayed" | "held"` or
  `"email": "delayed"` otherwise. It reveals no counts or host names.
- `UPTIVORA_HEARTBEAT_URL`: the worker requests it every minute while healthy (e.g. a
  healthchecks.io check); missing pings mean the server or worker is down.

`UPTIVORA_NETWORK_CANARIES` (set in `.env.example`) keeps a network outage of this server from
emailing every customer; [runbooks.md](runbooks.md) covers each health state. Run
`docker compose run --rm api python -m app.cli preflight --smtp` after every configuration
change.
