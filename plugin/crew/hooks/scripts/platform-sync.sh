#!/usr/bin/env bash
# SessionStart hook. Detects this machine and repairs .crew/config.json's
# platform block. config.json is machine-local -- `.crew/*` is ignored and the
# un-ignore list is codemap/, endpoints.json, verify.json, none of them this
# file -- so the block is not wrong because it travelled to another clone. It
# goes wrong in place: one checkout opened from Windows and from WSL is two
# machines sharing one config, and WSL2's windowsHostIp changes on reboot.
#
# Thin wrapper on purpose. The logic lives in crew_platform.py so the bash and
# PowerShell paths cannot drift, and the once-per-session claim lives there too
# so both flavours share one implementation of it. This matters more here than
# elsewhere: a hook that WRITES config must not have two implementations that
# disagree about what it writes.
#
# `crew_py_strict`, NOT `crew_py`. Same defect the old PM hooks had: a
# WindowsApps stub resolves under `command -v`, `exec` launches it, and it
# produces no output -- nothing left behind to notice or report the failure.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/_common.sh"
PY=$(crew_py_strict) || { echo "crew platform-sync: no usable python (stub or unusable interpreter) - the platform config will not be repaired" >&2; exit 0; }
exec "$PY" "$DIR/crew_platform.py"
