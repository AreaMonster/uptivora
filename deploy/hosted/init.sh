#!/bin/sh
# One-time preparation of the hosted deployment directory. Never overwrites anything.
set -eu
cd "$(dirname "$0")"
[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "Created .env — review every value."; }
mkdir -p secrets backups
chmod 700 secrets
for name in secret_key db_password; do
	if [ ! -s "secrets/$name" ]; then
		head -c 96 /dev/urandom | base64 | tr -d '\n/+=' | head -c 64 > "secrets/$name"
		echo "Generated secrets/$name"
	fi
done
for name in smtp_password stripe_webhook_secret; do
	[ -f "secrets/$name" ] || : > "secrets/$name"
done
chmod 644 secrets/*
echo "Put the SMTP password into secrets/smtp_password, then: docker compose up -d"
