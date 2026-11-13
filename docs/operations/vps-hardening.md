# VPS hardening checklist

For the hosted production server (Debian 12/13 or Ubuntu 24.04 LTS). Customers running the
self-hosted edition can use the same list.

## Access

- [ ] Create a non-root user `deploy` with sudo; add it to the `docker` group only if you
      accept that this equals root.
- [ ] SSH keys only: in `/etc/ssh/sshd_config.d/10-hardening.conf`
      ```
      PasswordAuthentication no
      KbdInteractiveAuthentication no
      PermitRootLogin no
      AllowUsers deploy
      ```
- [ ] Hardware-backed or passphrase-protected SSH keys; no shared keys between people.
- [ ] `fail2ban` (sshd jail) or restrict SSH to known addresses in the provider firewall.

## Updates

- [ ] `unattended-upgrades` for security updates, with automatic reboot at a quiet hour or
      a weekly manual reboot.
- [ ] Docker from Docker's apt repository so it receives updates.

## Firewall

- [ ] Inbound: 22 (restricted), 80, 443/tcp, 443/udp. Nothing else — PostgreSQL is never
      published. See [firewall.md](firewall.md), including the Docker/ufw caveat.

## Docker

- [ ] `/etc/docker/daemon.json`:
      ```json
      { "live-restore": true, "no-new-privileges": true,
        "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
      ```
- [ ] The compose files already run every Uptivora container read-only, unprivileged,
      without capabilities, and the database on an internal network.

## Secrets

- [ ] `deploy/hosted/secrets/` is mode 700 and owned by `deploy`; copies live in the password
      manager, not in git, chat or tickets.
- [ ] The licence **signing** key never touches this server ([../LICENSE_KEY_OPERATIONS.md](../LICENSE_KEY_OPERATIONS.md)).

## Time, disk, logs

- [ ] `systemd-timesyncd` or chrony active (TLS checks and certificate expiry depend on it).
- [ ] Alert when the disk is 80 % full (database + backups grow).
- [ ] Container logs rotate via the json-file options above; journald capped with
      `SystemMaxUse=1G`.

## Before go-live

- [ ] Restore test from an off-site backup completed.
- [ ] External uptime check on `/api/health/ready` from another provider.
- [ ] `https://` scores A+ on an SSL test; HSTS present.
