#!/bin/bash
#
# AI-Connect installation for Linux (Windows: install.cmd)
#
# Usage:
#   ./install.sh --client          # Client: venv, config, Claude Code (no service, no sudo)
#   ./install.sh --server          # Server: Bridge service + everything the client gets
#   ./install.sh --server --vpn-subnet=10.0.0.0/24  # firewall hint's remote scope, default is Tailscale's 100.64.0.0/10
#   ./install.sh --client --http   # also the HTTP/SSE service for other MCP clients
#   ./install.sh --update          # Update; detects what is installed
#   ./install.sh --status          # Show status
#   ./install.sh --uninstall       # Uninstall
#
# Config and the Claude Code registration are platform independent and live
# in installer.py; this script does the Linux part: venv and systemd.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/ai-connect"
PYTHON="$SCRIPT_DIR/venv/bin/python"
BRIDGE_UNIT=/etc/systemd/system/ai-connect.service
HTTP_UNIT=/etc/systemd/system/ai-connect-mcp.service
POLKIT_RULE=/etc/polkit-1/rules.d/50-ai-connect.rules

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

MODE=""          # "server" or "client"
HTTP=false
UPDATE=false
STATUS=false
UNINSTALL=false
# Only this range should reach the Bridge port; AI-Connect has no TLS of its own
VPN_SUBNET="100.64.0.0/10"

usage() {
    sed -n '3,13p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case $arg in
        --server) MODE="server" ;;
        --client) MODE="client" ;;
        --http) HTTP=true ;;
        --vpn-subnet=*) VPN_SUBNET="${arg#--vpn-subnet=}" ;;
        --update) UPDATE=true ;;
        --status) STATUS=true ;;
        --uninstall) UNINSTALL=true ;;
        --help|-h) usage; exit 0 ;;
        *) echo -e "${RED}Unknown option: $arg${NC}"; usage; exit 1 ;;
    esac
done

show_status() {
    echo ""
    echo -e "${BLUE}=== AI-Connect status ===${NC}"
    for UNIT in ai-connect ai-connect-mcp; do
        if [[ -f "/etc/systemd/system/$UNIT.service" ]]; then
            if systemctl is-active --quiet "$UNIT"; then
                echo -e "  $UNIT.service: ${GREEN}running${NC}"
            else
                echo -e "  $UNIT.service: ${RED}stopped${NC}"
            fi
        fi
    done
    if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
        echo -e "  Config: ${GREEN}$CONFIG_DIR/config.yaml${NC}"
    else
        echo -e "  Config: ${RED}missing${NC}"
    fi
    echo ""
}

do_uninstall() {
    read -p "Really uninstall AI-Connect? [y/N]: " CONFIRM
    [[ "$CONFIRM" =~ ^[yY]$ ]] || { echo "Aborted."; exit 0; }

    for UNIT in ai-connect-mcp ai-connect; do
        if [[ -f "/etc/systemd/system/$UNIT.service" ]]; then
            sudo systemctl disable --now "$UNIT" 2>/dev/null || true
            sudo rm "/etc/systemd/system/$UNIT.service"
            echo -e "  ${GREEN}$UNIT.service removed${NC}"
        fi
    done
    if [[ -f "$POLKIT_RULE" ]]; then
        sudo rm "$POLKIT_RULE"
        sudo systemctl restart polkit.service
    fi
    sudo systemctl daemon-reload 2>/dev/null || true

    if [[ -x "$PYTHON" ]]; then
        "$PYTHON" "$SCRIPT_DIR/installer.py" unregister
    else
        # No venv (a plugin update left this directory without one): installer.py cannot run, but the
        # state hooks it wrote into Claude Code's settings would stay and fail on every prompt.
        # state_hooks.py needs only the standard library, so any Python 3 takes them out.
        SYS_PYTHON=""
        for CANDIDATE in python3 python py; do
            if command -v "$CANDIDATE" >/dev/null 2>&1 && "$CANDIDATE" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
                SYS_PYTHON="$CANDIDATE"
                break
            fi
        done
        if [[ -n "$SYS_PYTHON" ]]; then
            "$SYS_PYTHON" "$SCRIPT_DIR/state_hooks.py" remove
        else
            echo -e "  ${RED}No Python 3 found (tried python3, python, py): the AI-Connect state hooks are still in Claude Code's settings.json. Remove the four peer_set_state hooks there by hand.${NC}" >&2
        fi
        echo "  No venv here, so the MCP server was not unregistered: claude mcp remove -s user ai-connect"
    fi

    read -p "Delete the config ($CONFIG_DIR) too? [y/N]: " DELETE_CONFIG
    if [[ "$DELETE_CONFIG" =~ ^[yY]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "  ${GREEN}Config deleted${NC}"
    fi
    echo ""
    echo "The venv stays; remove it with: rm -rf $SCRIPT_DIR/venv"
    exit 0
}

if $UNINSTALL; then do_uninstall; fi
if $STATUS; then show_status; exit 0; fi

# An update keeps what is installed: the services tell server and HTTP,
# the config tells a plain client
if $UPDATE; then
    if [[ -f "$BRIDGE_UNIT" ]]; then MODE="server"; else MODE="client"; fi
    [[ -f "$HTTP_UNIT" ]] && HTTP=true
    if [[ "$MODE" == "client" && ! -f "$CONFIG_DIR/config.yaml" ]]; then
        echo -e "${RED}No installation found. Install first.${NC}"
        exit 1
    fi
fi

if [[ -z "$MODE" ]]; then
    echo "Which installation?"
    echo -e "  ${YELLOW}1)${NC} Client - joins a Bridge running elsewhere"
    echo -e "  ${YELLOW}2)${NC} Server - this machine runs the Bridge (includes the client)"
    read -p "Choice [1/2]: " CHOICE
    case $CHOICE in
        1) MODE="client" ;;
        2) MODE="server" ;;
        *) echo -e "${RED}Invalid choice. Aborted.${NC}"; exit 1 ;;
    esac
    read -p "Also the HTTP/SSE service for other MCP clients (VS Code, Cursor, ...)? [y/N]: " WANT_HTTP
    [[ "$WANT_HTTP" =~ ^[yY]$ ]] && HTTP=true
fi

echo ""
echo -e "${BLUE}=== AI-Connect $MODE $($UPDATE && echo update || echo installation) ===${NC}"

echo -e "${YELLOW}[1/4]${NC} Python venv and dependencies..."
[[ -d "$SCRIPT_DIR/venv" ]] || python3 -m venv "$SCRIPT_DIR/venv"
"$PYTHON" -m pip install -q --upgrade pip
"$PYTHON" -m pip install -q --upgrade -r "$SCRIPT_DIR/requirements.txt"
echo -e "  ${GREEN}Dependencies up to date${NC}"

echo -e "${YELLOW}[2/4]${NC} Configuration..."
"$PYTHON" "$SCRIPT_DIR/installer.py" config --"$MODE"

echo -e "${YELLOW}[3/4]${NC} Claude Code..."
"$PYTHON" "$SCRIPT_DIR/installer.py" claude

echo -e "${YELLOW}[4/4]${NC} Services..."
install_unit() {
    local UNIT=$1 DESCRIPTION=$2 MODULE=$3 AFTER=$4
    sudo tee "/etc/systemd/system/$UNIT.service" > /dev/null << EOF
[Unit]
Description=$DESCRIPTION
After=network.target $AFTER

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON -m $MODULE
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
}

configure_firewall() {
    # install.ps1 creates an equivalent Windows Firewall rule itself (scoped
    # to -VpnSubnet, port 9999, Private profile); here we do the same with
    # whatever firewall manager is present, or fall back to printing the
    # command so the operator can run it themselves.
    local PORT=9999
    local FAMILY="ipv4"
    [[ "$VPN_SUBNET" == *:* ]] && FAMILY="ipv6"

    if [[ $EUID -ne 0 ]] && ! sudo -n true 2>/dev/null; then
        echo -e "  ${YELLOW}Firewall:${NC} not root and no passwordless sudo; skipping. Allow port $PORT only from your VPN ($VPN_SUBNET) yourself, e.g."
        echo "    sudo ufw allow from $VPN_SUBNET to any port $PORT proto tcp"
        return
    fi

    if command -v ufw >/dev/null 2>&1; then
        if sudo ufw status | grep -q "$PORT.*$VPN_SUBNET"; then
            echo -e "  ${GREEN}Firewall: ufw rule for $VPN_SUBNET on port $PORT already present${NC}"
        else
            sudo ufw allow from "$VPN_SUBNET" to any port "$PORT" proto tcp comment 'AI-Connect Bridge' >/dev/null
            echo -e "  ${GREEN}Firewall: ufw allow from $VPN_SUBNET to port $PORT added${NC}"
        fi
    elif command -v firewall-cmd >/dev/null 2>&1; then
        local RULE="rule family=\"$FAMILY\" source address=\"$VPN_SUBNET\" port port=\"$PORT\" protocol=\"tcp\" accept"
        if sudo firewall-cmd --permanent --query-rich-rule="$RULE" >/dev/null 2>&1; then
            echo -e "  ${GREEN}Firewall: firewalld rule for $VPN_SUBNET on port $PORT already present${NC}"
        else
            sudo firewall-cmd --permanent --add-rich-rule="$RULE" >/dev/null
            sudo firewall-cmd --reload >/dev/null
            echo -e "  ${GREEN}Firewall: firewalld rule for $VPN_SUBNET on port $PORT added${NC}"
        fi
    else
        echo -e "  ${YELLOW}Firewall:${NC} neither ufw nor firewalld found; allow port $PORT only from your VPN ($VPN_SUBNET) yourself, e.g."
        echo "    sudo ufw allow from $VPN_SUBNET to any port $PORT proto tcp"
    fi
}

UNITS=()
[[ "$MODE" == "server" ]] && UNITS+=(ai-connect)
$HTTP && UNITS+=(ai-connect-mcp)

if [[ ${#UNITS[@]} -eq 0 ]]; then
    echo "  None needed for a client (Claude Code starts its own MCP client per session)"
else
    echo "  (needs sudo)"
    [[ "$MODE" == "server" ]] && install_unit ai-connect "AI-Connect Bridge Server" server.main ""
    [[ "$MODE" == "server" ]] && configure_firewall
    $HTTP && install_unit ai-connect-mcp "AI-Connect MCP HTTP Server" client.http_server \
        "$([[ "$MODE" == "server" ]] && echo ai-connect.service)"

    # Lets this user restart the services without sudo
    UNIT_CHECK=$(printf 'action.lookup("unit") == "%s.service" || ' "${UNITS[@]}")
    sudo tee "$POLKIT_RULE" > /dev/null << EOF
// PolicyKit rule for the AI-Connect services: user '$USER' may control them
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        subject.user == "$USER" &&
        (${UNIT_CHECK% || })) {
        return polkit.Result.YES;
    }
});
EOF
    sudo chmod 644 "$POLKIT_RULE"
    sudo systemctl restart polkit.service
    sudo systemctl daemon-reload
    for UNIT in "${UNITS[@]}"; do
        sudo systemctl enable "$UNIT" 2>/dev/null
        sudo systemctl restart "$UNIT"
        echo -e "  ${GREEN}$UNIT.service running${NC}"
    done
fi

show_status
if [[ "$MODE" == "server" ]]; then
    echo "Each other machine needs its own peer token: $PYTHON $SCRIPT_DIR/installer.py add-peer <name>"
    echo "  (on that machine, put the printed token in client.token and <name> in client.name)"
fi
echo "Behaviour rules for Claude Code: add this line to ~/.claude/CLAUDE.md"
echo "  @$SCRIPT_DIR/integrations/claude-code/CLAUDE.md"
if $HTTP; then
    echo ""
    echo "Other MCP clients connect to http://127.0.0.1:9998/sse"
fi
echo ""
