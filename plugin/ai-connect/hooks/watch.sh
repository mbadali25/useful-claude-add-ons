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

# The tools below are looked up on a fixed PATH, not on one a project's settings could set; the
# caller's PATH is put back before the watcher starts.
ORIG_PATH="$PATH"
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
# CDPATH makes a relative `cd` land somewhere else, and a relative HOME is a project-relative path
# once the project is the working directory: neither is accepted.
unset CDPATH
# CLAUDE_PROJECT_DIR is set by Claude Code, but a project's settings could set it to a path that
# does not exist, which would leave only the working directory as "the project". Set and
# unresolvable is not trusted: no variable-chosen venv.
PROJ_BAD=0
if [ -n "${CLAUDE_PROJECT_DIR:-}" ] && ! (cd "$CLAUDE_PROJECT_DIR" 2>/dev/null); then
    PROJ_BAD=1
fi
case "${HOME:-}" in
    /*) ;;
    *) HOME="" ;;
esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WATCHER="integrations/claude-code/aiconnect_watch.py"
# The installer writes this outside the plugin directory (config_loader.py's
# CONFIG_PATH), so it survives a plugin update and tells "never set up" from
# "set up, then the venv went with the old plugin directory".
# HOME comes from the environment, which a project's settings can set; the account database
# cannot be set that way. A HOME that is not the account's home directory and lies inside the
# project the session runs in is ignored (as if unset): a repository cannot move "the user's
# home" into itself. Other HOMEs are left alone (a test or a container may set its own).
ACCT_HOME="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"
# Where the account database cannot be read (macOS has no getent), ACCT_HOME stays empty and a
# HOME inside the project is ignored; a HOME elsewhere is left alone.
if [ -n "${HOME:-}" ]; then
    _h="$(cd "$HOME" 2>/dev/null && pwd -P)"
    if [ -z "$ACCT_HOME" ] || [ "$_h" != "$(cd "$ACCT_HOME" 2>/dev/null && pwd -P)" ]; then
        for _proj in "${CLAUDE_PROJECT_DIR:-}" "$PWD"; do
            [ -n "$_proj" ] || continue
            _p="$(cd "$_proj" 2>/dev/null && pwd -P)" || continue
            # With the account home unknown a HOME inside the project is ignored too
            case "$_h/" in "$_p"/*) HOME="$ACCT_HOME"; export HOME ;; esac
        done
    fi
fi
CONFIG="${HOME:-}/.config/ai-connect/config.yaml"

# AI_CONNECT_VENV and AI_CONNECT_HOME choose which interpreter this hook starts on every
# SessionStart and Stop, and a project's settings.json can set environment variables. So a
# value is used only when it names a directory that is an absolute path with no '..', that
# lies under the user's own home (real paths compared), and that is not inside the project
# the session runs in (the current directory, CLAUDE_PROJECT_DIR): a repository cannot
# plant the interpreter this hook runs. A value that fails is ignored, as if unset.
HOME_REAL=""
if [ -n "${HOME:-}" ]; then
    HOME_REAL="$(cd "$HOME" 2>/dev/null && pwd -P)" || HOME_REAL=""
fi
trusted_dir() {
    [ "$PROJ_BAD" = 0 ] || return 1
    case "$1" in /*) ;; *) return 1 ;; esac
    case "/$1/" in */../*) return 1 ;; esac
    _real="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
    [ -n "$HOME_REAL" ] || return 1
    case "$_real/" in "$HOME_REAL"/*) ;; *) return 1 ;; esac
    for _proj in "${CLAUDE_PROJECT_DIR:-}" "$PWD"; do
        [ -n "$_proj" ] || continue
        _p="$(cd "$_proj" 2>/dev/null && pwd -P)" || continue
        # A project directory that is the home or above it holds everything under the home
        case "$HOME_REAL/" in "$_p"/*) continue ;; esac
        case "$_real/" in "$_p"/*) return 1 ;; esac
    done
    return 0
}

# Where deploy/deploy.py (deploy.sh, setup.sh) installs: deploy_core.py's
# APP_HOME, with the venv in it and a copy of the plugin beside that. Empty
# when there is neither a trusted AI_CONNECT_HOME nor a HOME to look under.
DEPLOY_HOME=""
if [ -n "${AI_CONNECT_HOME:-}" ] && trusted_dir "$AI_CONNECT_HOME"; then
    DEPLOY_HOME="$AI_CONNECT_HOME"
elif [ -n "${HOME:-}" ]; then
    DEPLOY_HOME="$HOME/.local/share/ai-connect"
fi

# The first venv that is there, in this order. watch.ps1 has the same three.
#   1. AI_CONNECT_VENV, the variable deploy_core.py reads for its venv (trusted, see above)
#   2. the plugin directory's own venv, where install.sh creates it
#   3. deploy's venv
# APP is the directory the watcher script is run from. With deploy's venv it is
# deploy's copy of the plugin when that holds the watcher (`deploy bridge`,
# `deploy peer --register-mcp`): the MCP server of this machine runs from that
# copy, with that venv. `deploy peer --install-hooks` alone makes the venv and
# no copy, and then the watcher is this plugin's own.
# Anything chosen through a variable needs the config too: a machine that was never set
# up stays silent whatever the variables say.
PYTHON=""
APP="$ROOT"
if [ -e "$CONFIG" ] && [ -n "${AI_CONNECT_VENV:-}" ] && [ -x "$AI_CONNECT_VENV/bin/python" ] \
        && trusted_dir "$AI_CONNECT_VENV" \
        && [ -n "$(find "$AI_CONNECT_VENV/bin/python" -maxdepth 0 -user "$(id -u)" 2>/dev/null)" ]; then
    PYTHON="$AI_CONNECT_VENV/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
    PYTHON="$ROOT/venv/bin/python"
elif [ -n "$DEPLOY_HOME" ] && [ -x "$DEPLOY_HOME/venv/bin/python" ] \
        && { [ -e "$CONFIG" ] || [ "$DEPLOY_HOME" = "${HOME:-}/.local/share/ai-connect" ]; }; then
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
    # not come along; deploy's lives outside it and does. The message names
    # places, not the values of the variables.
    echo "ai-connect watch.sh: no venv found (looked in $ROOT/venv, in deploy's ~/.local/share/ai-connect/venv or under AI_CONNECT_HOME, and at AI_CONNECT_VENV; a variable that is not an absolute path under your home, outside the project, is ignored) - run $ROOT/install.sh --client (again after each plugin update), or $ROOT/deploy/deploy.sh peer (or deploy/setup.sh) once" >&2
    exit 1
fi
# A project's settings can set PYTHONPATH, PYTHONPYCACHEPREFIX and the like, which would make a
# trusted interpreter import the repository's code: every PYTHON* variable is dropped.
# macOS's venv launcher variable steers the interpreter's home the same way
unset __PYVENV_LAUNCHER__
for _v in $(env | sed -n 's/^\(PYTHON[A-Za-z0-9_]*\)=.*/\1/p'); do
    unset "$_v"
done
PATH="$ORIG_PATH"
exec "$PYTHON" "$APP/$WATCHER"
