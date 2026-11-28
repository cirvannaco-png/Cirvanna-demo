#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

python --version
python - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        f"Cirvanna Codespaces requires Python 3.12; found {sys.version.split()[0]}"
    )
PY

git --version
docker --version

if [ ! -d .venv ]; then
  python -m venv .venv
fi

cat <<'EOF'
Cirvanna Codespaces is ready.

A repository-local virtual environment was created at .venv.
Install dependencies only for the service you intend to work on:
  bash .devcontainer/scripts/test-service.sh services/decision-service

Start disposable local PostgreSQL when required:
  bash .devcontainer/scripts/start-postgres.sh

No production credentials or databases are configured by this environment.
EOF
