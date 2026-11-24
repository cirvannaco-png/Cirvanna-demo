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

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  python -m venv "$ROOT/.venv"
fi
PYTHON="$ROOT/.venv/bin/python"

"$PYTHON" - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        f"Cirvanna tests require Python 3.12; found {sys.version.split()[0]}"
    )
PY

cd "$SERVICE_DIR"

if [ -f requirements.txt ]; then
  "$PYTHON" -m pip install -r requirements.txt
fi
if [ -f requirements-dev.txt ]; then
  "$PYTHON" -m pip install -r requirements-dev.txt
fi

if [ ! -d tests ]; then
  echo "No tests/ directory found in $SERVICE_PATH." >&2
  exit 2
fi

"$PYTHON" -m pytest -q
