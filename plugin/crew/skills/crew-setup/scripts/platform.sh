#!/usr/bin/env bash
# Detects OS, WSL variant, and available toolchain. Read-only. Emits JSON.
os="unknown"; wsl="no"; wsl_ver=""; distro=""; winhost=""; repo_fs="native"

case "$(uname -s 2>/dev/null)" in
  Linux*)  os="linux" ;;
  Darwin*) os="macos" ;;
  MINGW*|MSYS*|CYGWIN*) os="windows-bash" ;;   # Git Bash / MSYS on Windows
esac

if [ "$os" = "linux" ]; then
  if grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease 2>/dev/null; then
    wsl="yes"
    distro="${WSL_DISTRO_NAME:-$(grep -m1 '^ID=' /etc/os-release 2>/dev/null | cut -d= -f2)}"
    if grep -qi 'wsl2' /proc/sys/kernel/osrelease 2>/dev/null || [ -n "$WSL_INTEROP" ]; then
      wsl_ver="2"
    else
      wsl_ver="1"
    fi
    # WSL2: services on the Windows host are NOT on localhost
    winhost=$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}')
    # repo on the Windows filesystem is dramatically slower
    case "$(pwd -P)" in /mnt/[a-z]/*) repo_fs="windows-mount" ;; esac
  fi
fi

have() { command -v "$1" >/dev/null 2>&1 && echo true || echo false; }

# CRLF line endings break shell scripts with "bad interpreter"
crlf=false
for f in scripts/smoke.sh .crew/*.sh; do
  [ -f "$f" ] && head -1 "$f" | grep -q $'\r' && crlf=true
done

cat <<JSON
{
  "os": "$os",
  "wsl": "$wsl",
  "wslVersion": "$wsl_ver",
  "distro": "$distro",
  "windowsHostIp": "$winhost",
  "repoFilesystem": "$repo_fs",
  "shell": "bash",
  "tools": {
    "git": $(have git), "docker": $(have docker), "jq": $(have jq),
    "python3": $(have python3), "node": $(have node), "npx": $(have npx),
    "dotnet": $(have dotnet), "php": $(have php), "composer": $(have composer),
    "terraform": $(have terraform), "aws": $(have aws), "az": $(have az),
    "psql": $(have psql), "codex": $(have codex), "pwsh": $(have pwsh)
  },
  "crlfDetected": $crlf
}
JSON
