#!/usr/bin/env bash
# deploy: one-command Bridge / peer setup for AI-Connect. All logic lives in deploy.py,
# so this script and deploy.ps1 run the same steps in the same order with the same text.
#   ./deploy.sh bridge [--peer NAME ...] [--dry-run]
#   ./deploy.sh peer --name NAME --bridge IP --token-file F --auth-key-file F [--dry-run]
#   ./deploy.sh status
#   ./deploy.sh uninstall --yes [--purge] [--dry-run]
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../vpn/_common.sh
source "$here/../vpn/_common.sh"
if ! py="$(vpn_python)"; then
  echo "ai-connect deploy: no working Python 3 found on PATH (tried python3, python, py)" >&2
  exit 1
fi
exec "$py" "$here/deploy.py" "$@"