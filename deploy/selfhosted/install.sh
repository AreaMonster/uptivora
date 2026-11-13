#!/bin/sh
# One-time preparation of an Uptivora self-hosted installation. Safe to run again:
# existing configuration and secrets are never overwritten.
set -eu
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }

command -v docker >/dev/null 2>&1 || { say "Docker is not installed. See docs/selfhosted/install.md"; exit 1; }
docker compose version >/dev/null 2>&1 || { say "The Docker Compose plugin is missing (docker compose)."; exit 1; }

if [ ! -f .env ]; then
	cp .env.example .env
	chmod 600 .env
	say "Created .env — edit UPTIVORA_DOMAIN and the SMTP settings before starting."
else
	say "Keeping existing .env"
fi

mkdir -p secrets license backups
# The directory keeps other host users out; the files must stay readable for the
# unprivileged container users that mount them.
chmod 700 secrets

random_secret() {
	# 64 characters from the kernel CSPRNG, URL-safe alphabet.
	head -c 96 /dev/urandom | base64 | tr -d '\n/+=' | head -c "$1"
}

for name in secret_key db_password; do
	if [ ! -s "secrets/$name" ]; then
		random_secret 64 > "secrets/$name"
		say "Generated secrets/$name"
	fi
	chmod 644 "secrets/$name"
done
[ -f secrets/smtp_password ] || : > secrets/smtp_password
chmod 644 secrets/smtp_password

for archive in images/*.tar.gz images/*.tar; do
	[ -f "$archive" ] || continue
	say "Loading $(basename "$archive") ..."
	docker load -i "$archive"
done

say ""
say "Next steps:"
say "  1. Edit .env (domain, SMTP) and put the SMTP password into secrets/smtp_password"
say "  2. Optional: copy your licence file to license/uptivora.license"
say "  3. docker compose up -d"
say "  4. Open https://<your domain> — the first account becomes the administrator."
say ""
say "Keep a copy of secrets/ with your backups: the secret key signs the unsubscribe links"
say "in alert emails that were already sent."
