# Troubleshooting

Start with the state of the containers and the logs:

```bash
docker compose ps
docker compose logs --tail 100 api worker
docker compose logs --tail 50 caddy
```

Warnings and errors also appear under Admin → Logs, and Admin → System shows the database,
the workers and the email queue.

## The site does not load / certificate error

- `docker compose logs caddy` mentions *challenge failed*: DNS does not point at this server
  yet, or ports 80/443 are blocked by a firewall. Fix it; Caddy retries on its own.
- Rate-limited by the certificate authority after many failed attempts: wait an hour.
- Intranet without public DNS: use `UPTIVORA_TLS=internal` ([install.md](install.md#intranet-installations)).

## "Cross-site request blocked" when signing in

The address in the browser differs from `UPTIVORA_DOMAIN` / `UPTIVORA_PUBLIC_URL` (another host
name, or a port). Set `UPTIVORA_PUBLIC_URL` to exactly the address users open and run
`docker compose up -d`.

## A container keeps restarting

| Container | Typical cause |
| --- | --- |
| `migrate` exits with an error | Database not reachable or a dump from a newer version was restored |
| `api` / `worker`: *UPTIVORA_SECRET_KEY must be ...* | `secrets/secret_key` is empty — run `./install.sh` again |
| `api` / `worker`: *password authentication failed* | `secrets/db_password` was changed after the first start (see below) |
| `db`: *permission denied* | The `pgdata` volume was created by another tool; restore from backup into a fresh volume |

**Database password changed by mistake.** The password is set when the database is first
created. Put the original back into `secrets/db_password`, or change it inside the database:

```bash
docker compose exec db psql -U uptivora -c "ALTER USER uptivora PASSWORD '<content of secrets/db_password>'"
```

## No emails arrive

1. Admin → Logs shows each failed attempt with the error from your SMTP server (wrong
   password, sender not allowed, TLS mismatch).
2. Port 465 needs `UPTIVORA_SMTP_SECURITY=tls`, port 587 `starttls`.
3. Look in spam; set up SPF/DKIM ([smtp.md](smtp.md)).

## A monitor says "address not allowed"

Uptivora refuses URLs that resolve to private or reserved addresses (your LAN, localhost,
cloud metadata). This protects the server from being used to scan internal networks and
cannot be switched off. Monitor such systems through their public address.

## All monitors show as down at the same time

Usually the server lost its own internet connection or DNS. Check from the server:

```bash
docker compose exec worker python -c "import socket; print(socket.getaddrinfo('example.com', 443)[0][4])"
```

## Monitors were paused

Monitors paused because of the licence limit exceed your licence. Install the licence or a larger
edition, and they resume automatically.

## Getting help

Include `docker compose ps`, the relevant log lines and your Uptivora version
(`UPTIVORA_VERSION` in `.env`) — remove email addresses and domains you do not want to share.
