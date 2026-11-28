#!/usr/bin/env bash
set -euo pipefail

CONTAINER="cirvanna-dev-postgres"
VOLUME="cirvanna-dev-postgres-data"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is unavailable. Rebuild the Codespace and try again." >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker start "$CONTAINER" >/dev/null
else
  docker volume create "$VOLUME" >/dev/null
  docker run --detach \
    --name "$CONTAINER" \
    --publish 5432:5432 \
    --env POSTGRES_USER=cirvanna_dev \
    --env POSTGRES_PASSWORD=cirvanna_dev_only \
    --env POSTGRES_DB=cirvanna_dev \
    --volume "$VOLUME:/var/lib/postgresql/data" \
    postgres:16-alpine >/dev/null
fi

for attempt in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U cirvanna_dev -d cirvanna_dev >/dev/null 2>&1; then
    echo "Disposable PostgreSQL is ready on localhost:5432."
    echo "Database: cirvanna_dev | User: cirvanna_dev"
    echo "Password: cirvanna_dev_only (local development only)"
    exit 0
  fi
  sleep 2
done

echo "PostgreSQL did not become ready. Inspect: docker logs $CONTAINER" >&2
exit 1
