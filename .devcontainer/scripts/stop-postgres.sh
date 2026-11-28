#!/usr/bin/env bash
set -euo pipefail

CONTAINER="cirvanna-dev-postgres"
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker stop "$CONTAINER" >/dev/null
  echo "Stopped disposable PostgreSQL. Its local named volume was retained."
else
  echo "Disposable PostgreSQL container does not exist."
fi
