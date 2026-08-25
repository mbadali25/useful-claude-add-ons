#!/usr/bin/env bash
# Shared helpers for crew hook scripts. Sourced, never run directly.
#
# Two problems this solves:
#   1. Every hook is registered once, as bash. The PreToolUse guard hands off
#      to its .ps1 twin when the command being judged is PowerShell - the
#      branch is which TOOL was used, not which OS is running. The other hooks
#      judge no command, and are reached through `bash`, so bash does the work.
#   2. python3 is not a given. Git Bash ships without it, and every script
#      here parses hook JSON from stdin.

# Hand control to the PowerShell twin when the command being judged is
# PowerShell. The branch is WHICH TOOL Claude used, not which OS you are on:
# a Bash-tool command is bash syntax even on Windows, and judging it with
# PowerShell rules blocks the correct capture form and misses the wrong one.
#
# $1 = twin filename, $2 = the raw hook JSON (already read from stdin).
crew_tool_dispatch() {
  case "$2" in
    *'"tool_name"'*'"PowerShell"'*) ;;
    *) return 0 ;;
  esac
  local twin
  twin="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)/$1"
  [ -f "$twin" ] || return 0
  local ps
  ps=$(command -v powershell.exe 2>/dev/null || command -v pwsh.exe 2>/dev/null \
       || command -v powershell 2>/dev/null || command -v pwsh 2>/dev/null) || return 0
  printf '%s' "$2" | "$ps" -NoProfile -ExecutionPolicy Bypass -File "$twin"
  exit $?   # NOT exec: on the right of a pipe it replaces the subshell only
}

# Strip carriage returns. jq and some Windows tools emit CRLF, and a trailing
# CR breaks every regex anchored with $.
crew_strip_cr() { printf '%s' "$1" | tr -d '\r'; }

# Resolve a usable Python. Echoes nothing when there is none.
crew_py() {
  command -v python3 2>/dev/null && return 0
  command -v python  2>/dev/null && return 0
  command -v py      2>/dev/null && return 0
  return 1
}

# --- Emergency lane -------------------------------------------------------
#
# Is an incident open, unexpired, and allowed to stand the gates down?
# See hooks/scripts/crew_incident.py for the file format: expiresAtEpoch is an
# integer of seconds so the comparison is arithmetic rather than a date parse,
# which in bash would mean a date(1) that behaves differently on macOS.
#
# Four separate conditions, deliberately not collapsed:
#   1. a state file exists
#   2. emergency.standDown is not false (a repo can forbid stand-downs)
#   3. it PARSES as JSON, in full
#   4. the clock has not passed the expiry
#
# (4) is the safety property: forgetting to close an incident cannot leave a
# repository permanently ungated. (3) is why this parses instead of grepping the
# epoch out with sed: `{ not json "expiresAtEpoch": 9999999999` is not a valid
# incident, but sed would happily find a future epoch in it and stand every gate
# down, while the PowerShell twin's ConvertFrom-Json rejects the document. That
# is a gate that can be switched off with a typo, and one that behaves
# differently per flavour.
#
# Every failure here - including no python at all - returns "not active", so the
# gates keep gating. That is the only safe direction: a gate that cannot read
# its own state must not assume it has been told to stand down.
crew_incident_active() {
  [ -f .crew/incident.json ] || return 1
  grep -q '"standDown"[[:space:]]*:[[:space:]]*false' .crew/config.json 2>/dev/null && return 1
  local py exp now
  py=$(crew_py) || return 1
  exp=$("$py" - << 'PY' 2>/dev/null
import json
try:
    d = json.load(open(".crew/incident.json", encoding="utf-8"))
    print(int(d["expiresAtEpoch"]) if isinstance(d, dict) else 0)
except Exception:
    print(0)
PY
)
  [ -n "$exp" ] || return 1
  [ "$exp" -gt 0 ] 2>/dev/null || return 1
  now=$(date -u +%s 2>/dev/null) || return 1
  [ "$now" -lt "$exp" ]
}

# Record a gate that did not run. $1 = gate name, $2 = detail.
#
# One row per gate+detail per incident, not per turn. Stop fires every turn and
# on Windows with Git Bash installed BOTH flavours of the hook run, so a
# ten-turn incident would otherwise report forty skipped gates - a number that
# measures how long the incident lasted, not what is owed. The closing report
# is a debt list, and the same unrun check is one debt however many times the
# gate declined to run it. crew_incident.log_skip applies the same rule.
crew_incident_log() {
  mkdir -p .crew 2>/dev/null
  local row gate detail
  # The log is tab-separated and line-oriented, and a detail can carry an
  # environment name, a rollback path or a rollbackReason straight out of
  # .crew/verify.json. A tab or a newline in one of those would forge a row.
  # crew_incident.py normalises the same way.
  gate=$(printf '%s' "$1" | tr '\t\r\n' '   ')
  detail=$(printf '%s' "$2" | tr '\t\r\n' '   ')
  row="$(printf '%s\t%s' "$gate" "$detail")"
  # -F: the detail is prose and contains regex metacharacters. Anchored to
  # after the epoch field, so a detail cannot match a different gate's row.
  if [ -f .crew/incident-skips.log ] \
     && cut -f2- .crew/incident-skips.log | grep -qxF "$row"; then
    return 0
  fi
  # Best-effort dedupe: two hook flavours appending at the same instant can both
  # miss the row above. The consequence is a duplicated line in a debt list, not
  # a gate that failed to fire, and crew_incident.read_skips dedupes again on
  # read so the count stays right either way. Not worth a lock file.
  printf '%s\t%s\n' "$(date -u +%s)" "$row" >> .crew/incident-skips.log
}

# Read one top-level string field out of hook JSON on stdin.
# Usage: crew_json_field "$INPUT" transcript_path
crew_json_field() {
  local py; py=$(crew_py) || return 1
  printf '%s' "$1" | "$py" -c \
    'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$2" 2>/dev/null
}
