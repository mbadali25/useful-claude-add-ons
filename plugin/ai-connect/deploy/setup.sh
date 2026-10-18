#!/usr/bin/env bash
# setup: from "plugin installed" to a working AI-Connect peer in one run. All logic lives in
# peer_setup.py, so this script and setup.ps1 take the same options in the same order and print the same text.
# Without --apply it prints the plan and changes nothing.
#   ./setup.sh bridge [--peer NAME ...] [--enrol NAME=SHA256 ...] [--register-mcp] [--apply]
#   ./setup.sh peer --name NAME --bridge IP [--token-file F | --invite-file F] [--register-mcp] [--apply]
#   ./setup.sh session --name NAME [--apply]
#   ./setup.sh session --project DIR [--project DIR ...] [--apply]
# It never runs `deploy tailnet-setup` (the owner's step: it replaces the tailnet policy).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=../vpn/_common.sh
source "$here/../vpn/_common.sh"
if ! py="$(vpn_python)"; then
  echo "ai-connect setup: no working Python 3 found on PATH (tried python3, python, py)" >&2
  exit 1
fi
exec "$py" "$here/peer_setup.py" "$@"
