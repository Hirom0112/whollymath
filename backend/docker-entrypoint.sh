#!/usr/bin/env bash
# Container entrypoint for the WhollyMath backend.
#
# Responsibilities, in order:
#   1. Assemble DATABASE_URL from the individual RDS credential env vars that
#      ECS injects from Secrets Manager (DB_HOST/DB_PORT/DB_NAME/DB_USER/
#      DB_PASSWORD), URL-encoding the username and password.
#   2. Apply the database schema and seed the curriculum catalog via
#      `alembic upgrade head`. This MUST succeed — in prod we never want the
#      app to silently fall back to its in-memory/SQLite mode.
#   3. exec uvicorn so it becomes PID 1 and receives SIGTERM from ECS.
set -euo pipefail

# --- 1. Assemble DATABASE_URL ---------------------------------------------
# Only build it from parts if it isn't already provided and the RDS host is
# present. This lets a caller override DATABASE_URL directly (e.g. local runs)
# while ECS supplies the discrete Secrets Manager fields.
if [[ -z "${DATABASE_URL:-}" && -n "${DB_HOST:-}" ]]; then
    : "${DB_PORT:=5432}"

    # URL-encode user and password — they may contain characters (@ : / etc.)
    # that would corrupt the connection URL otherwise.
    ENC_USER="$(python -c "import os,urllib.parse as u; print(u.quote(os.environ['DB_USER'], safe=''))")"
    ENC_PASS="$(python -c "import os,urllib.parse as u; print(u.quote(os.environ['DB_PASSWORD'], safe=''))")"

    export DATABASE_URL="postgresql://${ENC_USER}:${ENC_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

    # Redacted confirmation — never log the password.
    echo "entrypoint: assembled DATABASE_URL for host=${DB_HOST}:${DB_PORT} db=${DB_NAME}"
elif [[ -n "${DATABASE_URL:-}" ]]; then
    echo "entrypoint: using pre-set DATABASE_URL"
else
    echo "entrypoint: WARNING — no DATABASE_URL and no DB_HOST; app will use its env-default backend"
fi

# --- 2. Apply migrations (schema + curriculum seed) -----------------------
# cwd is /app, where alembic.ini lives. Fail fast on any migration error.
echo "entrypoint: running 'alembic upgrade head'"
alembic upgrade head

# --- 3. Hand off to uvicorn -----------------------------------------------
echo "entrypoint: starting uvicorn on 0.0.0.0:8000"
exec uvicorn app.api.app:app --host 0.0.0.0 --port 8000
