#!/bin/sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=/backups}"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$BACKUP_DIR/resume-matcher-$stamp.dump"

pg_dump --format=custom --no-owner --no-privileges --file="$backup" "$DATABASE_URL"
sha256sum "$backup" > "$backup.sha256"
printf '%s\n' "$backup"
