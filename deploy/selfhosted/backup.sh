#!/bin/sh
# Uptivora database backups (runs inside the postgres image as the "backup" service).
#
#   schedule          dump every day at BACKUP_TIME (default 02:30), keep BACKUP_KEEP_DAYS (14)
#   now               write one dump immediately
#   list              show existing dumps
#   verify FILE       restore FILE into a scratch database and check it, then drop it
#   restore FILE      replace the live database with FILE (stop api, worker and web first)
#
# Dumps are PostgreSQL custom-format files in /backups (./backups on the host).
set -eu

DIR=/backups
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
AT="${BACKUP_TIME:-02:30}"
PGPASSWORD="$(cat /run/secrets/db_password)"
export PGPASSWORD
export PGHOST="${PGHOST:-db}" PGUSER="${PGUSER:-uptivora}" PGDATABASE="${PGDATABASE:-uptivora}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') backup: $*"; }

dump_now() {
	umask 077
	ts="$(date -u +%Y%m%dT%H%M%SZ)"
	part="$DIR/.uptivora-$ts.dump.partial"
	# zstd: about a third of the size of gzip for this data (PostgreSQL 16+; restores of
	# older gzip dumps keep working, pg_restore detects the format).
	pg_dump --format=custom --compress=zstd:9 --no-owner --no-privileges --file="$part"
	mv "$part" "$DIR/uptivora-$ts.dump"
	log "wrote uptivora-$ts.dump ($(du -h "$DIR/uptivora-$ts.dump" | cut -f1))"
	find "$DIR" -maxdepth 1 -type f -name 'uptivora-*.dump' -mtime +"$KEEP_DAYS" -print -delete |
		while read -r old; do log "removed $(basename "$old") (older than $KEEP_DAYS days)"; done
	find "$DIR" -maxdepth 1 -type f -name '.uptivora-*.partial' -mmin +360 -delete
}

seconds_until_next_run() {
	now="$(date +%s)"
	target="$(date -d "$(date +%Y-%m-%d) $AT" +%s)"
	[ "$target" -gt "$now" ] || target=$((target + 86400))
	echo $((target - now))
}

resolve_file() {
	case "$1" in
		/*) echo "$1" ;;
		*) echo "$DIR/$1" ;;
	esac
}

case "${1:-schedule}" in
	schedule)
		log "scheduled daily at $AT ($(date +%Z)), keeping $KEEP_DAYS days in $DIR"
		trap 'exit 0' TERM INT
		while :; do
			wait_s="$(seconds_until_next_run)"
			sleep "$wait_s" &
			wait $!
			dump_now || log "FAILED — check the database connection and free disk space"
		done
		;;
	now)
		dump_now
		;;
	list)
		ls -lh "$DIR"/uptivora-*.dump 2>/dev/null || echo "No backups in $DIR yet."
		;;
	verify)
		file="$(resolve_file "${2:?usage: verify FILE}")"
		scratch="uptivora_verify_$$"
		createdb "$scratch"
		trap 'dropdb --if-exists "$scratch"' EXIT
		pg_restore --no-owner --no-privileges --exit-on-error --dbname="$scratch" "$file"
		users="$(psql -d "$scratch" -Atc 'SELECT count(*) FROM users')"
		monitors="$(psql -d "$scratch" -Atc 'SELECT count(*) FROM monitors')"
		rev="$(psql -d "$scratch" -Atc 'SELECT version_num FROM alembic_version')"
		log "OK: $(basename "$file") restores cleanly — $users users, $monitors monitors, schema $rev"
		;;
	restore)
		file="$(resolve_file "${2:?usage: restore FILE}")"
		[ -f "$file" ] || { log "no such file: $file"; exit 1; }
		log "restoring $(basename "$file") into database $PGDATABASE — current data will be replaced"
		pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error \
			--single-transaction --dbname="$PGDATABASE" "$file"
		log "restore complete. Start the application again: docker compose up -d"
		;;
	*)
		echo "usage: $0 schedule|now|list|verify FILE|restore FILE" >&2
		exit 2
		;;
esac
