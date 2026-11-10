#!/bin/sh
# L-0728 amendment 2026-10-20. The image's `codex` on PATH: Codex's own sandbox cannot start in a
# Docker container on this host (bwrap: Failed to make / slave), so every
# `--sandbox read-only` is rewritten to `--sandbox danger-full-access` and the container
# (no host mounts beyond the run's repo and home, an --internal network, the allowlisting
# proxy, no secrets beyond short-lived access tokens) is the only boundary. Nothing else is
# changed. CODEX_REAL overrides the real binary (the suite's stub).
real="${CODEX_REAL:-/usr/local/bin/codex}"
prev=""
n=$#
while [ "$n" -gt 0 ]; do
  orig="$1"
  shift
  arg="$orig"
  if [ "$prev" = "--sandbox" ] || [ "$prev" = "-s" ]; then
    case "$orig" in read-only) arg="danger-full-access" ;; esac
  else
    case "$orig" in
      --sandbox=read-only) arg="--sandbox=danger-full-access" ;;
      -s=read-only) arg="-s=danger-full-access" ;;
    esac
  fi
  prev="$orig"
  set -- "$@" "$arg"
  n=$((n - 1))
done
exec "$real" "$@"
