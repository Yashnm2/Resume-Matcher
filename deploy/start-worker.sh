#!/bin/sh
set -eu
cd /app/backend
queue="${WORKER_QUEUE:?Set WORKER_QUEUE to discovery, llm, or render}"
case "$queue" in
  discovery) concurrency="${WORKER_CONCURRENCY:-4}" ;;
  llm) concurrency="${WORKER_CONCURRENCY:-2}" ;;
  render) concurrency="${WORKER_CONCURRENCY:-1}" ;;
  *) echo "Unsupported WORKER_QUEUE=$queue" >&2; exit 2 ;;
esac
exec celery -A app.celery_app.celery_app worker -Q "$queue" --concurrency="$concurrency" --loglevel="${LOG_LEVEL:-INFO}"
