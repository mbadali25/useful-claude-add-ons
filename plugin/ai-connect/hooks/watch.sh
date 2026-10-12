#!/bin/sh
# SessionStart / Stop asyncRewake hook: runs the AI-Connect message watcher
# with this plugin's venv. Exit 2 wakes the session (a message arrived),
# 0 = another watcher already runs or AI-Connect was never set up on this
# machine, 1 = error (reason on stderr).
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
# The installer writes this outside the plugin directory (config_loader.py's
# CONFIG_PATH), so it survives a plugin update and tells "never set up" from
# "set up, then the venv went with the old plugin directory".
CONFIG="${HOME:-}/.config/ai-connect/config.yaml"
if [ ! -x "$PYTHON" ]; then
    if [ ! -e "$CONFIG" ]; then
        # Never set up: the plugin is installed but its installer has not run.
        # Nothing to watch and nothing to report: say nothing on every event.
        exit 0
    fi
    # The plugin cache directory changes on every plugin update, and the venv
    # lives inside it, so an update leaves the new directory without one.
    echo "ai-connect watch.sh: no venv at $ROOT/venv - run $ROOT/install.sh --client (again after each plugin update)" >&2
    exit 1
fi
exec "$PYTHON" "$ROOT/integrations/claude-code/aiconnect_watch.py"
