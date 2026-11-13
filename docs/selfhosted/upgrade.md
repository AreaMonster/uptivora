# Upgrading

Upgrades are included in your licence. Uptivora never downloads them by itself; you decide
when to upgrade. Read the release notes first — they mention anything that needs attention.

## Steps

```bash
cd /opt/uptivora                                   # your installation directory
docker compose exec backup uptivora-backup now      # 1. fresh backup

tar xzf ~/uptivora-selfhosted-<new>.tar.gz          # 2. unpack the new bundle elsewhere
docker load -i uptivora-selfhosted-<new>/images/uptivora-<new>.tar.gz
cp uptivora-selfhosted-<new>/compose.yaml uptivora-selfhosted-<new>/Caddyfile \
   uptivora-selfhosted-<new>/backup.sh .            # 3. replace the stack files

sed -i 's/^UPTIVORA_VERSION=.*/UPTIVORA_VERSION=<new>/' .env   # 4. switch version
docker compose up -d                                # 5. migrate and restart
docker compose ps
```

Your `.env`, `secrets/`, `license/` and `backups/` stay as they are. Compare the new
`.env.example` with your `.env` for new optional settings.

Database migrations run automatically (`migrate` service) before the new version starts.
Releases that restructure stored data say so in the release notes; on large installations
such a migration can take several minutes, during which no checks run. Otherwise monitoring
pauses for the few seconds the containers need to restart; checks that were due
in that time run right after.

## Rolling back

Migrations only move forward. To go back to the previous version:

```bash
docker compose stop api worker web
docker compose exec backup uptivora-backup restore <the dump from step 1>
sed -i 's/^UPTIVORA_VERSION=.*/UPTIVORA_VERSION=<old>/' .env
docker compose up -d
```

Results recorded between the upgrade and the rollback are lost.

## PostgreSQL and Caddy

`postgres:17-alpine` and `caddy:2-alpine` receive security fixes within their major
version. Pull them from time to time:

```bash
docker compose pull db caddy backup && docker compose up -d
```

A new PostgreSQL *major* version is announced in the release notes together with the
migration steps; it is never switched silently.
