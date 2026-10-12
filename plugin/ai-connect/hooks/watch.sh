#!/bin/sh
# SessionStart / Stop asyncRewake hook: runs the AI-Connect message watcher
# with this plugin's venv. Exit 2 wakes the session (a message arrived),
# 0 = another watcher already runs, 1 = error (reason on stderr).
#
# Flavour guard. hooks.json registers this and watch.ps1 for the same events,
# and on Windows Claude Code runs both (this one through Git Bash). Stand down
# there and let watch.ps1 run, so one session never starts two watchers.
# $OS is 'Windows_NT' in Git Bash on Windows and unset on Linux/macOS.
if [ "${OS:-}" = "Windows_NT" ]; then
    exit 0
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    # The plugin cache directory changes on every plugin update, and the venv
    # lives inside it, so an update leaves the new directory without one.
    echo "ai-connect watch.sh: no venv at $ROOT/venv - run $ROOT/install.sh --client (again after each plugin update)" >&2
    exit 1
fi
exec "$PYTHON" "$ROOT/integrations/claude-code/aiconnect_watch.py"
