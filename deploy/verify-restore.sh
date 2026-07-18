#!/bin/sh
set -eu

: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL must point to an isolated restore database}"
: "${BACKUP_FILE:?BACKUP_FILE is required}"

if [ "${DATABASE_URL:-}" = "$RESTORE_DATABASE_URL" ]; then
  echo "Refusing to restore into the production DATABASE_URL" >&2
  exit 2
fi

sha256sum --check "$BACKUP_FILE.sha256"
pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$RESTORE_DATABASE_URL" "$BACKUP_FILE"

psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS search_profiles FROM search_profiles;
SELECT COUNT(*) AS postings FROM job_postings;
SELECT COUNT(*) AS packs FROM artifact_packs;
SELECT COUNT(*) AS audit_events FROM audit_events;
SQL
