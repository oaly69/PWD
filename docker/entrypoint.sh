#!/bin/sh
set -e
mkdir -p "${PWD_DATA_DIR:-/data}"
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port "${PWD_PORT:-8080}" --proxy-headers --forwarded-allow-ips='*'
