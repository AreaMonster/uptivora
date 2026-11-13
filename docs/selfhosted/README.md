# Uptivora self-hosted

Uptivora checks your websites around the clock and emails you when one goes down, comes back,
or its certificate is about to expire. This bundle runs the whole product on your own server.
It never contacts Uptivora: the licence is checked locally, there is no update check and no
telemetry.

## Quick start

On a Linux server with Docker and a DNS name pointing at it:

```bash
tar xzf uptivora-selfhosted-<version>.tar.gz && cd uptivora-selfhosted-<version>
./install.sh                      # creates .env and secrets/, loads the images
nano .env                         # domain and SMTP settings
nano secrets/smtp_password        # SMTP password (may stay empty for an open relay)
docker compose up -d
```

Open `https://<your domain>`. The first account you create becomes the administrator.

## Guides

| Guide | |
| --- | --- |
| [install.md](install.md) | Requirements, installation, what runs where, intranet installs |
| [smtp.md](smtp.md) | Setting up outgoing email, provider examples, testing delivery |
| [licence.md](licence.md) | Installing, replacing and removing the licence file |
| [backups.md](backups.md) | Automatic backups, copying them off the server, restoring |
| [upgrade.md](upgrade.md) | Installing a new version, rolling back |
| [troubleshooting.md](troubleshooting.md) | Common problems and how to read the logs |

## What is in this directory

```
compose.yaml       the services (do not edit; put settings in .env)
.env               your settings
secrets/           generated database password and secret key, your SMTP password
license/           put uptivora.license here (optional)
backups/           nightly database dumps
Caddyfile          HTTPS reverse proxy configuration
backup.sh          backup / restore tool used by the backup service
install.sh         one-time setup, safe to re-run
images/            the Uptivora images for offline installation
```
