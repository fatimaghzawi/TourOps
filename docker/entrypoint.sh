#!/bin/sh
set -eu

mkdir -p /app/data /app/media /app/staticfiles
chown -R appuser:appuser /app/data /app/media /app/staticfiles

run_as_app() {
  gosu appuser "$@"
}

echo "Waiting for MongoDB..."
run_as_app python - <<'PY'
import os
import sys
import time

from pymongo import MongoClient
from pymongo.errors import PyMongoError

uri = os.environ.get("MONGODB_URI", "mongodb://mongo:27017")
for attempt in range(30):
    try:
        MongoClient(uri, serverSelectionTimeoutMS=2000).admin.command("ping")
        print("MongoDB is ready.")
        sys.exit(0)
    except PyMongoError:
        time.sleep(1)
print("MongoDB did not become ready in time.", file=sys.stderr)
sys.exit(1)
PY

run_as_app python manage.py migrate --noinput
run_as_app python manage.py collectstatic --noinput
run_as_app python manage.py ensure_indexes

workers="${GUNICORN_WORKERS:-3}"
exec gosu appuser gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "$workers" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
