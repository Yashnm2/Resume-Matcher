#!/bin/sh
set -eu
cd /app/backend
exec celery -A app.celery_app.celery_app beat --loglevel="${LOG_LEVEL:-INFO}"
