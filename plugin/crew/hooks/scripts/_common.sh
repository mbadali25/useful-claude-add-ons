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

# Read one top-level string field out of hook JSON on stdin.
# Usage: crew_json_field "$INPUT" transcript_path
crew_json_field() {
  local py; py=$(crew_py) || return 1
  printf '%s' "$1" | "$py" -c \
    'import sys,json;print(json.load(sys.stdin).get(sys.argv[1],""))' "$2" 2>/dev/null
}
