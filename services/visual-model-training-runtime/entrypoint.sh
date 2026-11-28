#!/usr/bin/env bash
set -euo pipefail
mkdir -p /tmp/cvi-home
export HOME=/tmp/cvi-home
if [[ -d /workspace/source/.git ]]; then
  git config --global --add safe.directory /workspace/source
fi
exec "$@"
