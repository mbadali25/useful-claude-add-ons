#!/usr/bin/env bash
# Set up claude-obsidian on Linux (native).
#
# Standards shared with the Windows/WSL script (setup-claude-obsidian.ps1):
#   * dry-run by default; nothing is changed without --apply
#   * every check reports PASS / FIX / FAIL with a stable check id
#   * identical vault layout, marketplaces, plugins and verification
#   * idempotent: safe to re-run; already-satisfied steps are skipped
#   * exits non-zero if any check is still FAIL after the run
#
# Usage:
#   bash setup-claude-obsidian.sh                 # preview only
#   bash setup-claude-obsidian.sh --apply
#   bash setup-claude-obsidian.sh --apply --vault ~/vaults/Claude
set -uo pipefail

APPLY=0
# Everything lives under one root so a single flag relocates the whole setup.
# ~/repos is the Linux counterpart of the Windows default C:\repos; --repo-root
# moves it, and --vault / --product override either half individually.
REPO_ROOT="${HOME}/repos"
VAULT=""
PRODUCT=""
SKIP_PLUGINS=0
SKIP_OBSIDIAN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --repo-root) REPO_ROOT="$2"; shift ;;
    --vault) VAULT="$2"; shift ;;
    --product) PRODUCT="$2"; shift ;;
    --skip-plugins) SKIP_PLUGINS=1 ;;
    --skip-obsidian) SKIP_OBSIDIAN=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

[ -n "$VAULT" ]   || VAULT="${REPO_ROOT}/Claude"
[ -n "$PRODUCT" ] || PRODUCT="${REPO_ROOT}/claude-obsidian"

FAILED=0
pass() { printf '  \033[32mPASS\033[0m  %-28s %s\n' "$1" "${2:-}"; }
fix()  { printf '  \033[33mFIX \033[0m  %-28s %s\n' "$1" "${2:-}"; }
fail() { printf '  \033[31mFAIL\033[0m  %-28s %s\n' "$1" "${2:-}"; FAILED=1; }
head2(){ printf '\n\033[1m== %s\033[0m\n' "$1"; }
run() {
  # run <description> <command...>
  local desc="$1"; shift
  if [ "$APPLY" -eq 1 ]; then
    if "$@" >/tmp/co-setup.log 2>&1; then
      fix "$desc" "done"
    else
      fail "$desc" "failed - see /tmp/co-setup.log"
      tail -3 /tmp/co-setup.log | sed 's/^/        /'
    fi
  else
    fix "$desc" "would run: $*"
  fi
}

echo "claude-obsidian setup (linux)"
echo "  mode    : $([ "$APPLY" -eq 1 ] && echo APPLY || echo 'DRY-RUN (pass --apply to change anything)')"
echo "  root    : $REPO_ROOT   (change with --repo-root)"
echo "  vault   : $VAULT"
echo "  product : $PRODUCT"

# --------------------------------------------------------------------------
head2 "1. Prerequisites"
# --------------------------------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then PKG=apt-get
elif command -v dnf >/dev/null 2>&1; then PKG=dnf
elif command -v pacman >/dev/null 2>&1; then PKG=pacman
else PKG=""; fi
[ -n "$PKG" ] && pass "pkg-manager" "$PKG" || fail "pkg-manager" "none of apt-get/dnf/pacman found"

install_pkgs() {
  case "$PKG" in
    apt-get) sudo apt-get update -qq && sudo apt-get install -y "$@" ;;
    dnf)     sudo dnf install -y "$@" ;;
    pacman)  sudo pacman -Sy --noconfirm "$@" ;;
  esac
}

pkg_available() {
  # Is $1 offered by the repositories already configured on this machine?
  # Deliberately does not consult or add third-party repositories.
  case "$PKG" in
    apt-get) apt-cache show "$1" >/dev/null 2>&1 ;;
    dnf)     dnf -q list --available "$1" >/dev/null 2>&1 ;;
    pacman)  pacman -Si "$1" >/dev/null 2>&1 ;;
    *)       return 1 ;;
  esac
}
py_version_ok() {
  "$1" -c 'import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)' >/dev/null 2>&1
}

MISSING=()
PY=python3        # the interpreter every later step actually uses
PY_OK=0           # PY already clears the 3.11 floor
PY_PENDING=0      # PY does not clear it yet, but this run can repair it

# Python 3.11+ is the product's documented floor.
if command -v python3 >/dev/null 2>&1; then
  PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0.0)
  if py_version_ok python3; then
    pass "python3" "$PYV"
    PY_OK=1
  else
    # `python3` is too old. Rather than touch update-alternatives or add a
    # third-party repository, look for a newer *versioned* interpreter and use
    # that explicitly - first one already installed, then one the configured
    # repositories can supply. The system python3 is left exactly as it is.
    for c in python3.14 python3.13 python3.12 python3.11; do
      if command -v "$c" >/dev/null 2>&1 && py_version_ok "$c"; then
        PY="$c"; PY_OK=1
        pass "python3" "system python3 is $PYV; using $c instead"
        break
      fi
    done
    if [ "$PY_OK" -ne 1 ]; then
      CAND=""
      for c in python3.13 python3.12 python3.11; do
        if pkg_available "$c"; then CAND="$c"; break; fi
      done
      if [ -z "$CAND" ]; then
        fail "python3" "$PYV found, 3.11+ required, and no newer python3 in the configured repositories - add one (e.g. the deadsnakes PPA on Ubuntu 22.04) or use a newer distro"
      elif [ "$APPLY" -eq 0 ]; then
        PY_PENDING=1
        fix "python3" "$PYV too old - would install $CAND alongside it and use that"
      elif install_pkgs "$CAND" >/dev/null 2>&1 && command -v "$CAND" >/dev/null 2>&1 && py_version_ok "$CAND"; then
        PY="$CAND"; PY_OK=1
        fix "python3" "installed $CAND alongside the system python3 ($PYV) and using it"
      else
        fail "python3" "installing $CAND failed - install python3.11+ by hand and re-run"
      fi
    fi
  fi
else
  # Absent is repairable in this same run, so it is a FIX, not a FAIL - a FAIL
  # would leave the exit status at 1 even after we successfully install it.
  fix "python3" "not installed - will install"; MISSING+=(python3); PY_PENDING=1
fi

# fcntl.flock + POSIX directory descriptors are what make vault writes safe.
if command -v "$PY" >/dev/null 2>&1 && "$PY" -c 'import fcntl' >/dev/null 2>&1; then
  pass "python3-fcntl" "available via $PY (vault writes supported)"
elif [ "$PY_PENDING" -eq 1 ]; then
  # Can't know yet, and saying FAIL here would wrongly fail the whole run.
  fix "python3-fcntl" "unknown until python3 is installed"
else
  fail "python3-fcntl" "missing - vault writes will be refused"
fi

for c in git curl; do
  if command -v "$c" >/dev/null 2>&1; then pass "$c" "$(command -v "$c")"
  else fix "$c" "will install"; MISSING+=("$c"); fi
done

if command -v node >/dev/null 2>&1; then
  NODEV=$(node -v)
  pass "node" "$NODEV"
else
  fix "node" "will install (required by Claude Code)"
fi

if [ ${#MISSING[@]} -gt 0 ]; then
  run "install packages: ${MISSING[*]}" install_pkgs "${MISSING[@]}"
  # A distro that had no python3 may still package one below the floor, so
  # re-check rather than assume the install satisfied the requirement.
  if [ "$APPLY" -eq 1 ] && [ "$PY_OK" -ne 1 ] && command -v python3 >/dev/null 2>&1; then
    if py_version_ok python3; then
      PY_OK=1; PY_PENDING=0
      pass "python3" "installed $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
    else
      PY_PENDING=0
      fail "python3" "installed python3 is still below 3.11 - install python3.11+ by hand and re-run"
    fi
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  # NodeSource publishes .deb repositories only, so it is correct for apt and
  # wrong everywhere else. Fedora and Arch package a current Node themselves.
  case "$PKG" in
    apt-get) node_how="NodeSource (Debian/Ubuntu ship an older Node)" ;;
    dnf|pacman) node_how="the distro package (nodejs, npm)" ;;
    *) node_how="" ;;
  esac
  if [ -z "$node_how" ]; then
    fail "node" "no supported package manager to install Node with"
  elif [ "$APPLY" -eq 0 ]; then
    fix "node" "would install Node via $node_how"
  elif [ "$PKG" = "apt-get" ]; then
    if curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - >/tmp/co-setup.log 2>&1 \
       && install_pkgs nodejs >>/tmp/co-setup.log 2>&1; then
      fix "node" "installed via NodeSource"
    else
      fail "node" "install failed - see /tmp/co-setup.log"
    fi
  else
    run "install node via $PKG" install_pkgs nodejs npm
  fi
fi

if command -v claude >/dev/null 2>&1; then
  pass "claude-code" "$(claude --version 2>/dev/null | head -1)"
else
  run "install Claude Code" npm install -g @anthropic-ai/claude-code
fi

# Obsidian desktop. Distro repos rarely carry it, so prefer flatpak/snap, which
# are the two routes upstream actually publishes to.
if command -v obsidian >/dev/null 2>&1 \
   || flatpak info md.obsidian.Obsidian >/dev/null 2>&1 \
   || [ -d /snap/obsidian ]; then
  pass "obsidian" "installed"
elif [ "$SKIP_OBSIDIAN" -eq 1 ]; then
  pass "obsidian" "skipped (--skip-obsidian)"
elif command -v flatpak >/dev/null 2>&1; then
  run "install Obsidian (flatpak)" flatpak install -y flathub md.obsidian.Obsidian
elif command -v snap >/dev/null 2>&1; then
  run "install Obsidian (snap)" sudo snap install obsidian --classic
else
  fix "obsidian" "no flatpak or snap - install from https://obsidian.md (AppImage/.deb)"
fi

# --------------------------------------------------------------------------
head2 "2. Product checkout"
# --------------------------------------------------------------------------
if [ -f "$PRODUCT/scripts/claude-obsidian.py" ]; then
  pass "product" "$PRODUCT"
else
  # git clone does create missing parent directories, but creating the parent
  # explicitly removes the dependency on that behaviour and keeps the failure
  # mode obvious if the root is not writable.
  [ "$APPLY" -eq 1 ] && mkdir -p "$(dirname "$PRODUCT")"
  run "clone product to $PRODUCT" git clone --depth 1 \
    https://github.com/AgriciDaniel/claude-obsidian.git "$PRODUCT"
fi
CORE="$PRODUCT/scripts/claude-obsidian.py"

# --------------------------------------------------------------------------
head2 "3. Claude marketplaces and plugins"
# --------------------------------------------------------------------------
if [ "$SKIP_PLUGINS" -eq 1 ]; then
  pass "plugins" "skipped (--skip-plugins)"
elif ! command -v claude >/dev/null 2>&1 && [ "$APPLY" -eq 0 ]; then
  fix "plugins" "would add marketplaces + install plugins once claude exists"
else
  # claude-obsidian itself, plus Obsidian's own upstream syntax skills.
  run "marketplace: claude-obsidian" claude plugin marketplace add AgriciDaniel/claude-obsidian
  run "plugin: claude-obsidian"      claude plugin install claude-obsidian@agricidaniel-claude-obsidian
  run "marketplace: obsidian-skills" claude plugin marketplace add kepano/obsidian-skills
  run "plugin: obsidian"             claude plugin install obsidian@obsidian-skills
fi

# --------------------------------------------------------------------------
head2 "4. Vault"
# --------------------------------------------------------------------------
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ -f "$VAULT/.claude-obsidian.json" ]; then
  pass "vault" "$VAULT (already initialised)"
elif [ ! -f "$CORE" ]; then
  fix "vault" "waiting on product checkout"
elif [ "$PY_OK" -ne 1 ] && [ "$PY_PENDING" -ne 1 ]; then
  # An interpreter below the floor would fail somewhere deep inside the core.
  # Stop here so the actionable python3 message above is the last word.
  fail "vault" "blocked: python3 3.11+ is required to create a vault"
else
  if [ "$APPLY" -eq 1 ]; then
    # Nothing above this line may touch the filesystem: a dry-run must leave the
    # disk exactly as it found it, mkdir included.
    mkdir -p "$(dirname "$VAULT")"
    # The product's own preview-then-apply contract: never apply a plan that
    # was not just reviewed, and pass its emitted hash back unchanged.
    PLAN=$("$PY" "$CORE" init "$VAULT" --generated-at "$STAMP" \
             --operation-id init-reviewed 2>&1)
    HASH=$(printf '%s' "$PLAN" | grep -o '"approved_plan_sha256": "[a-f0-9]\{64\}"' \
             | head -1 | grep -o '[a-f0-9]\{64\}')
    if [ -z "$HASH" ]; then
      fail "vault init" "dry-run produced no approval hash"
      printf '%s\n' "$PLAN" | head -5 | sed 's/^/        /'
    else
      printf '%s\n' "$PLAN" | grep -A20 '"changed_paths"' | head -20 | sed 's/^/        /'
      if "$PY" "$CORE" init "$VAULT" --generated-at "$STAMP" \
           --operation-id init-reviewed --approved-plan-sha256 "$HASH" --apply \
           >/tmp/co-setup.log 2>&1; then
        fix "vault init" "created $VAULT"
      else
        fail "vault init" "$(head -1 /tmp/co-setup.log)"
      fi
    fi
  else
    fix "vault init" "would init $VAULT (preview, then apply with its hash)"
  fi
fi

# --------------------------------------------------------------------------
head2 "5. Git identity (needed by checkpoint)"
# --------------------------------------------------------------------------
if [ -d "$VAULT/.git" ]; then
  if git -C "$VAULT" config user.email >/dev/null 2>&1; then
    pass "git identity" "$(git -C "$VAULT" config user.email)"
  else
    fail "git identity" "set it: git -C $VAULT config user.email you@example.com"
  fi
else
  pass "git" "vault is not a repo (optional; checkpoint needs one)"
fi

# --------------------------------------------------------------------------
head2 "6. Verify"
# --------------------------------------------------------------------------
if [ -f "$CORE" ] && [ -f "$VAULT/.claude-obsidian.json" ]; then
  if "$PY" "$CORE" doctor --vault "$VAULT" 2>/dev/null | grep -q '"ok": true'; then
    pass "doctor" "ok"
  else
    fail "doctor" "not ok"
  fi
  ISSUES=$("$PY" "$CORE" lint --vault "$VAULT" 2>/dev/null \
           | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["summary"]["issues_found"])' 2>/dev/null || echo "?")
  [ "$ISSUES" = "0" ] && pass "lint" "0 issues" || fail "lint" "$ISSUES issue(s)"
else
  fix "verify" "runs once product and vault exist"
fi

head2 "Next"
cat <<EOF
  Obsidian    : open $VAULT via the vault picker
  Templates   : Settings > Templates > Template folder location = wiki/templates
  Daily notes : Settings > Daily notes > New file location = wiki/daily,
                date format YYYY-MM-DD
  CLI (opt.)  : Settings > General > enable "Command line interface"
  Skills      : /claude-obsidian:wiki
EOF

[ "$APPLY" -eq 0 ] && echo "
  DRY RUN - nothing changed. Re-run with --apply."
exit $FAILED
