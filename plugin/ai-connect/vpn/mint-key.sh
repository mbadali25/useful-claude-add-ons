#!/usr/bin/env bash
# mint-key: see README.md. All logic lives in tsadmin.py.
set -euo pipefail
# shellcheck source=_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
vpn_run mint-key "$@"
