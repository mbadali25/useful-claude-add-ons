#!/bin/sh
# SessionStart / Stop asyncRewake hook: runs the AI-Connect message watcher
# with the venv this machine was set up with. Exit 2 wakes the session (a
# message arrived), 0 = another watcher already runs or AI-Connect was never
# set up on this machine, 1 = error (reason on stderr).
#
# Flavour guard. hooks.json registers this and watch.ps1 for the same events,
# and on Windows Claude Code runs both (this one through Git Bash). Stand down
# there and let watch.ps1 run, so one session never starts two watchers.
# $OS is 'Windows_NT' in Git Bash on Windows and unset on Linux/macOS.
if [ "${OS:-}" = "Windows_NT" ]; then
    exit 0
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WATCHER="integrations/claude-code/aiconnect_watch.py"
# The installer writes this outside the plugin directory (config_loader.py's
# CONFIG_PATH), so it survives a plugin update and tells "never set up" from
# "set up, then the venv went with the old plugin directory".
CONFIG="${HOME:-}/.config/ai-connect/config.yaml"

# Where deploy/deploy.py (deploy.sh, setup.sh) installs: deploy_core.py's
# APP_HOME, with the venv in it and a copy of the plugin beside that. Empty
# when there is neither an AI_CONNECT_HOME nor a HOME to look under.
DEPLOY_HOME="${AI_CONNECT_HOME:-}"
if [ -z "$DEPLOY_HOME" ] && [ -n "${HOME:-}" ]; then
    DEPLOY_HOME="$HOME/.local/share/ai-connect"
fi

# The first venv that is there, in this order. watch.ps1 has the same three.
#   1. AI_CONNECT_VENV, the variable deploy_core.py reads for its venv
#   2. the plugin directory's own venv, where install.sh creates it
#   3. deploy's venv
# APP is the directory the watcher script is run from. With deploy's venv it is
# deploy's copy of the plugin when that holds the watcher (`deploy bridge`,
# `deploy peer --register-mcp`): the MCP server of this machine runs from that
# copy, with that venv. `deploy peer --install-hooks` alone makes the venv and
# no copy, and then the watcher is this plugin's own.
PYTHON=""
APP="$ROOT"
if [ -n "${AI_CONNECT_VENV:-}" ] && [ -x "$AI_CONNECT_VENV/bin/python" ]; then
    PYTHON="$AI_CONNECT_VENV/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
    PYTHON="$ROOT/venv/bin/python"
elif [ -n "$DEPLOY_HOME" ] && [ -x "$DEPLOY_HOME/venv/bin/python" ]; then
    PYTHON="$DEPLOY_HOME/venv/bin/python"
    if [ -f "$DEPLOY_HOME/app/$WATCHER" ]; then
        APP="$DEPLOY_HOME/app"
    fi
fi

if [ -z "$PYTHON" ]; then
    if [ ! -e "$CONFIG" ]; then
        # Never set up: the plugin is installed but no installer has run.
        # Nothing to watch and nothing to report: say nothing on every event.
        exit 0
    fi
    # Set up, and no venv anywhere it is looked for. The plugin cache directory
    # changes on every plugin update, so a venv install.sh made inside it does
    # not come along; deploy's lives outside it and does.
    LOOKED="$ROOT/venv"
    if [ -n "$DEPLOY_HOME" ]; then
        LOOKED="$LOOKED or $DEPLOY_HOME/venv"
    fi
    if [ -n "${AI_CONNECT_VENV:-}" ]; then
        LOOKED="$AI_CONNECT_VENV (AI_CONNECT_VENV) or $LOOKED"
    fi
    echo "ai-connect watch.sh: no venv at $LOOKED - run $ROOT/install.sh --client (again after each plugin update), or $ROOT/deploy/deploy.sh peer once" >&2
    exit 1
fi
exec "$PYTHON" "$APP/$WATCHER"
