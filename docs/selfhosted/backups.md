# Backups and restore

The `backup` service dumps the database every night at `BACKUP_TIME` (02:30 by default) into
`./backups` and deletes dumps older than `BACKUP_KEEP_DAYS` (14). The database holds
everything: accounts, monitors, history, settings and a licence installed in the web
interface.

Also keep, once, a copy of:

- `.env` and `secrets/` — the secret key signs the unsubscribe links in alerts already sent
- `license/` if you use a licence file

## Copy backups off the server

A backup on the same disk does not survive the loss of that disk. Copy `./backups`
somewhere else every day, for example with a cron job on another machine:

```bash
rsync -a --delete monitor.example.com:/opt/uptivora/backups/ /srv/backup/uptivora/
```

Dumps contain email addresses and password hashes: store them encrypted or on a trusted
system.

## Useful commands

```bash
docker compose exec backup uptivora-backup now        # take a backup now
docker compose exec backup uptivora-backup list       # list backups
docker compose exec backup uptivora-backup verify uptivora-20261113T013000Z.dump
```

`verify` restores a dump into a temporary database, checks it and drops it again. Run it
from time to time — a backup you have never restored is a hope, not a backup.

## Restore

Restoring replaces the entire database with the dump.

```bash
docker compose stop api worker web
docker compose exec backup uptivora-backup restore uptivora-20261113T013000Z.dump
docker compose up -d
```

`up -d` re-applies migrations, so you can restore a dump taken with an older version of
Uptivora. A dump from a *newer* version needs that newer version installed first.

## Restoring on a new server

1. Install the same (or a newer) Uptivora version with `install.sh`.
2. Copy over `.env`, `secrets/`, `license/` and the dump into `backups/`.
3. `docker compose up -d db backup`, then run the restore commands above.
4. Point DNS at the new server.
