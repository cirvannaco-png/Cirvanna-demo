#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SERVICE_PATH="${1:-services/decision-service}"

case "$SERVICE_PATH" in
  services/*|packages/*) ;;
  *)
    echo "Choose a service or package path under services/ or packages/." >&2
    exit 2
    ;;
esac

SERVICE_DIR="$ROOT/$SERVICE_PATH"
if [ ! -d "$SERVICE_DIR" ]; then
  echo "Directory not found: $SERVICE_PATH" >&2
  exit 2
fi

cd "$SERVICE_DIR"

if [ -f requirements.txt ]; then
  python -m pip install -r requirements.txt
fi
if [ -f requirements-dev.txt ]; then
  python -m pip install -r requirements-dev.txt
fi

if [ ! -d tests ]; then
  echo "No tests/ directory found in $SERVICE_PATH." >&2
  exit 2
fi

python -m pytest -q
