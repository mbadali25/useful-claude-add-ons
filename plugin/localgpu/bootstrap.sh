#!/usr/bin/env bash
# localgpu bootstrap (POSIX side). Twin of bootstrap.ps1 - same six steps, same order,
# same flag names and meanings. Idempotent: every step detects before it acts and
# reports "already installed" rather than reinstalling.
#
# What it stands up:
#   * an Ollama server on http://127.0.0.1:11434
#   * a Python venv at $LOCALGPU_HOME/venv with numpy (plus mcp/requirements.txt)
#   * the embedding model nomic-embed-text and the chat model
#     qwen2.5-coder:7b-instruct-q4_K_M
#   * OLLAMA_MAX_LOADED_MODELS=1, persistently, so two models never share the VRAM
#
# The six steps, in this order:
#   1. NVIDIA driver present, and report the compute capability
#   2. Ollama installed
#   3. venv + numpy
#   4. both models pulled
#   5. VRAM discipline env var
#   6. VERIFY - a real embed request, then 'ollama ps' proving GPU and not CPU offload
#
# Step 6 is the point of the whole script. On a Blackwell card (sm_120: the RTX 50xx
# series) an Ollama built against a CUDA runtime older than 12.8 has no kernel for the
# architecture and silently runs the model on the CPU instead. Everything still
# "works" - it is just an order of magnitude slower - so this script fails loudly on
# that rather than printing a green tick.
#
# Usage: ./bootstrap.sh [options]
#   --yes                 assume yes to every prompt (unattended)
#   --dry-run             print what each step would do, change nothing
#   --skip-models         skip step 4 (and the chat-model half of step 6)
#   --verify-only         run steps 1 and 6 only - no installing, no writing
#   --install-root <dir>  override $LOCALGPU_HOME
#   --help                print this usage and exit
#
# Install root: $LOCALGPU_HOME. Defaults to ~/.local/share/localgpu on real POSIX, but
# to %LOCALAPPDATA%/localgpu (the SAME root bootstrap.ps1 uses) when this is Git Bash or
# MSYS on Windows - both are reachable there, and picking the POSIX one unconditionally
# is exactly what split an install in two (T-0002). Index artifacts live under
# $LOCALGPU_HOME/index, the venv under $LOCALGPU_HOME/venv.

set -uo pipefail

OLLAMA_URL="http://127.0.0.1:11434"
EMBED_MODEL="nomic-embed-text"
CHAT_MODEL="qwen2.5-coder:7b-instruct-q4_K_M"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS="$SCRIPT_DIR/mcp/requirements.txt"

ASSUME_YES=0
DRY_RUN=0
SKIP_MODELS=0
VERIFY_ONLY=0
INSTALL_ROOT=""

usage() {
  # The banner comment above is the usage text; keeping one copy means the two can
  # never drift apart.
  sed -n '2,34p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,\} \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)       ASSUME_YES=1 ;;
    --dry-run)      DRY_RUN=1 ;;
    --skip-models)  SKIP_MODELS=1 ;;
    --verify-only)  VERIFY_ONLY=1 ;;
    --install-root) INSTALL_ROOT="${2:-}"; shift ;;
    --help|-h)      usage; exit 0 ;;
    *) printf 'Unknown option: %s (try --help)\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

# --- Output -------------------------------------------------------------------
step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()   { printf '    \033[32mOK:\033[0m %s\n' "$1"; }
warn() { printf '    \033[33mWARN:\033[0m %s\n' "$1"; }
skip() { printf '    \033[90mSKIP:\033[0m %s\n' "$1"; }
info() { printf '    %s\n' "$1"; }
note() { printf '        %s\n' "$1"; }

# Everything that ends the run goes to stderr. Under 'curl ... | bash' stdout is often
# being read by something else; a failure that only ever reached stdout is a failure
# nobody sees.
die() {
  printf '\n\033[31mFAIL: %s\033[0m\n' "$1" >&2
  shift
  local line
  for line in "$@"; do printf '      %s\n' "$line" >&2; done
  printf '\n' >&2
  exit 1
}

have() { command -v "$1" >/dev/null 2>&1; }

# Same detection skills/crew-setup/scripts/platform.sh already uses to report
# "os: windows-bash" on this exact machine shape - Git Bash and MSYS both report a
# MINGW*/MSYS* kernel name from uname, Cygwin a CYGWIN* one.
is_windows_bash() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
    *) return 1 ;;
  esac
}

posix_default_root() { printf '%s' "$HOME/.local/share/localgpu"; }

# Empty stdout and a non-zero return when $LOCALAPPDATA is not set at all (real POSIX).
windows_default_root() {
  [ -n "${LOCALAPPDATA:-}" ] || return 1
  if have cygpath; then
    printf '%s/localgpu' "$(cygpath -u "$LOCALAPPDATA")"
  else
    printf '%s/localgpu' "$LOCALAPPDATA"
  fi
}

# Ollama's installers put the binary somewhere a shell that was already running when it
# was installed does not have on PATH: /usr/local/bin on Linux, and on Windows the
# per-user %LOCALAPPDATA%\Programs\Ollama that the installer writes into the *registry*
# PATH, which a running Git Bash never re-reads. Believing PATH there reports "not
# installed" on a machine where Ollama is installed and serving - and step 2 then
# reinstalls it, which is exactly the non-idempotence every other step here avoids.
# So look in the known locations before concluding it is absent.
ensure_ollama_on_path() {
  have ollama && return 0
  local dir resolved
  for dir in \
    "/usr/local/bin" \
    "$HOME/.local/bin" \
    "${LOCALAPPDATA:-$HOME/AppData/Local}/Programs/Ollama" \
    "$HOME/AppData/Local/Programs/Ollama" \
    "${ProgramFiles:-/c/Program Files}/Ollama"
  do
    # A Windows-shaped path carries a drive colon, and PATH is colon-separated - putting
    # one in verbatim corrupts every later lookup. Convert first where cygpath exists.
    resolved="$dir"
    if have cygpath; then
      resolved="$(cygpath -u "$dir" 2>/dev/null)" || resolved="$dir"
    fi
    [ -n "$resolved" ] || continue
    case "$resolved" in *:*) continue ;; esac
    if [ -x "$resolved/ollama" ] || [ -x "$resolved/ollama.exe" ]; then
      PATH="$PATH:$resolved"
      export PATH
      hash -r 2>/dev/null || true
      have ollama && return 0
    fi
  done
  return 1
}

# =============================================================================
# The localgpu CLI's own PATH entry
# =============================================================================
# 'pip install -e' drops a working 'localgpu' console script in $VENV_DIR/bin (a POSIX
# venv) or $VENV_DIR/Scripts (a venv built by a Windows python on a Git Bash PATH) - pip
# never puts either on PATH, so 'localgpu shell' resolves only from inside the venv.
# Reuses ensure_ollama_on_path's handling above rather than a second copy of it: a
# Windows-shaped path carries a drive colon while PATH is colon-separated, and appending
# to a profile only reaches a NEW shell, never this one.
ensure_localgpu_on_path() {
  if [ "$DRY_RUN" -eq 1 ]; then
    info "Would expose the venv's script directory (bin or Scripts) on PATH, persistently"
    return 0
  fi

  local vpy scripts_dir resolved marker line wrote=0 rc
  vpy="$(venv_python)" || return 0
  scripts_dir="$(dirname "$vpy")"

  resolved="$scripts_dir"
  if have cygpath; then
    resolved="$(cygpath -u "$scripts_dir" 2>/dev/null)" || resolved="$scripts_dir"
  fi

  if [ ! -x "$scripts_dir/localgpu" ] && [ ! -x "$scripts_dir/localgpu.exe" ]; then
    return 0
  fi

  marker='# Added by localgpu bootstrap - exposes the venv console scripts'
  line="export PATH=\"$resolved:\$PATH\""

  for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ ! -f "$rc" ] && [ "$rc" != "$HOME/.profile" ]; then
      continue
    fi
    if [ -f "$rc" ] && grep -qF "$line" "$rc" 2>/dev/null; then
      skip "localgpu already on PATH via $rc"
      continue
    fi
    # A marker from an earlier run exists but points at a DIFFERENT root (e.g. the
    # install root moved under T-0002's fix): correct that line in place rather than
    # appending a second one, which is what left two marked blocks and made PATH a
    # coin flip on which root a new shell would pick up.
    if [ -f "$rc" ] && grep -qF "$marker" "$rc" 2>/dev/null; then
      local tmp
      tmp="$(mktemp)" || { warn "Could not create a temp file to fix $rc"; continue; }
      if awk -v m="$marker" -v l="$line" '
            $0==m { print; print l; skip=1; next }
            skip>0 { skip=0; next }
            { print }
          ' "$rc" > "$tmp" && mv "$tmp" "$rc"; then
        ok "Corrected stale PATH entry in $rc -> $resolved"
        wrote=1
      else
        rm -f "$tmp"
        warn "Could not rewrite $rc to correct the stale PATH entry"
      fi
      continue
    fi
    if { printf '\n%s\n%s\n' "$marker" "$line"; } >> "$rc" 2>/dev/null; then
      ok "Added $resolved to PATH in $rc"
      wrote=1
    else
      warn "Could not write to $rc"
    fi
  done

  # This process needs it now too, so the smoke check right after this run can see it.
  case ":$PATH:" in
    *":$resolved:"*) : ;;
    *) PATH="$resolved:$PATH"; export PATH; hash -r 2>/dev/null || true ;;
  esac

  if [ "$wrote" -eq 0 ]; then
    info "Nothing to change - localgpu is already persistent on PATH."
  fi

  have localgpu && ok "localgpu resolves: $(command -v localgpu)"
}

# Print instead of run, under --dry-run.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '    \033[90mDRY-RUN:\033[0m %s\n' "$*"
    return 0
  fi
  "$@"
}

# --- Install root -------------------------------------------------------------
# Priority: --install-root, then an explicit $LOCALGPU_HOME already in the caller's
# environment, then the platform default - which on Git Bash/MSYS is the WINDOWS
# default (bootstrap.ps1's), not the POSIX one, because both are reachable there and
# only one of them can be canonical.
if [ -n "$INSTALL_ROOT" ]; then
  LOCALGPU_HOME="$INSTALL_ROOT"
elif [ -n "${LOCALGPU_HOME:-}" ]; then
  : # honor the caller's environment as-is
elif is_windows_bash && WIN_DEFAULT="$(windows_default_root)"; then
  LOCALGPU_HOME="$WIN_DEFAULT"
else
  LOCALGPU_HOME="$(posix_default_root)"
fi
VENV_DIR="$LOCALGPU_HOME/venv"
INDEX_DIR="$LOCALGPU_HOME/index"

# --- Duplicate-install detection ------------------------------------------------
# On Git Bash/MSYS both the POSIX default and the Windows default are reachable, so if
# a venv exists at the one we did NOT pick, an old bug (T-0002) or a manual setup built
# an install twice - two venvs, two 'localgpu' binaries, and which one runs depends on
# which shell you're in. Never build a second one in silence: say which root is in use
# and which stray to remove. This never deletes anything itself.
check_other_root_duplicate() {
  is_windows_bash || return 0
  local wd pd other
  wd="$(windows_default_root 2>/dev/null)" || wd=""
  pd="$(posix_default_root)"
  if [ -n "$wd" ] && [ "$LOCALGPU_HOME" = "$wd" ] && [ "$pd" != "$wd" ]; then
    other="$pd"
  elif [ "$LOCALGPU_HOME" = "$pd" ] && [ -n "$wd" ] && [ "$wd" != "$pd" ]; then
    other="$wd"
  else
    return 0
  fi
  [ -d "$other/venv" ] || return 0

  warn "Also found a venv at $other - a DIFFERENT install root than the one in use."
  note "That is the split T-0002 fixed: two venvs, two 'localgpu' binaries, and which one"
  note "runs depends on which shell you're in. This run uses $LOCALGPU_HOME (canonical on"
  note "Windows - it's what bootstrap.ps1 already defaults to) and will NOT touch $other."
  note "Remove the stray install once you've confirmed it's not the one you want:"
  note "  rm -rf '$other'"
}
check_other_root_duplicate

# A venv built by a POSIX python puts its interpreter in bin/; one built by a Windows
# python that happens to be on a Git Bash PATH puts it in Scripts/. Resolve rather than
# assume, so --verify-only works against either.
venv_python() {
  if [ -x "$VENV_DIR/bin/python" ]; then printf '%s' "$VENV_DIR/bin/python"; return 0; fi
  if [ -x "$VENV_DIR/Scripts/python.exe" ]; then printf '%s' "$VENV_DIR/Scripts/python.exe"; return 0; fi
  return 1
}

# Git Bash ships without python3. Resolve the whole family and fail loudly - a silent
# fallback here produces a venv-less install that only breaks much later, at query time.
resolve_python() {
  local candidate
  for candidate in python3 python py; do
    have "$candidate" || continue
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

# --- HTTP ---------------------------------------------------------------------
# curl or wget, whichever is here. Both are asked for the body only; the caller checks
# the body, because a 200 carrying an error object is still a failure.
http_post() {
  local url="$1" body="$2" timeout="${3:-120}"
  if have curl; then
    curl -fsS --max-time "$timeout" -H 'Content-Type: application/json' -d "$body" "$url" 2>/dev/null
  elif have wget; then
    wget -qO- --timeout="$timeout" --header='Content-Type: application/json' \
      --post-data="$body" "$url" 2>/dev/null
  else
    return 127
  fi
}

http_get() {
  local url="$1" timeout="${2:-10}"
  if have curl; then
    curl -fsS --max-time "$timeout" "$url" 2>/dev/null
  elif have wget; then
    wget -qO- --timeout="$timeout" "$url" 2>/dev/null
  else
    return 127
  fi
}

printf '\033[36mlocalgpu bootstrap\033[0m\n'
info "install root : $LOCALGPU_HOME"
info "venv         : $VENV_DIR"
info "index        : $INDEX_DIR"
info "ollama       : $OLLAMA_URL"
[ "$DRY_RUN" -eq 1 ]     && info "mode         : --dry-run (nothing will be changed)"
[ "$VERIFY_ONLY" -eq 1 ] && info "mode         : --verify-only (steps 1 and 6 only)"

# =============================================================================
# Step 1 - NVIDIA driver and compute capability
# =============================================================================
GPU_NAME=""
GPU_CC=""
GPU_DRIVER=""
GPU_VRAM=""
IS_BLACKWELL=0

check_driver() {
  step "1/6  NVIDIA driver"

  if ! have nvidia-smi; then
    die "nvidia-smi is not on PATH, so there is no usable NVIDIA driver here." \
        "localgpu runs its models on the GPU; without a driver there is nothing to run" \
        "them on, and Ollama would fall back to the CPU without telling you." \
        "" \
        "Install the NVIDIA driver for this machine, reboot, confirm that 'nvidia-smi'" \
        "prints a table, then re-run this script."
  fi

  if ! nvidia-smi >/dev/null 2>&1; then
    die "nvidia-smi is installed but returned an error." \
        "That usually means the kernel module and the userspace driver are different" \
        "versions - most often after an unattended driver upgrade without a reboot." \
        "" \
        "Reboot, run 'nvidia-smi' by hand, and re-run this script once it prints a table."
  fi

  # compute_cap is a relatively recent query field. An older driver rejects it, which is
  # not fatal - we just cannot name the architecture in the step 6 diagnosis.
  local query
  query="$(nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total \
    --format=csv,noheader,nounits 2>/dev/null | head -n 1 | sed 's/\r$//')"
  if [ -n "$query" ]; then
    GPU_NAME="$(printf '%s'   "$query" | cut -d, -f1 | sed 's/^ *//; s/ *$//')"
    GPU_CC="$(printf '%s'     "$query" | cut -d, -f2 | sed 's/^ *//; s/ *$//')"
    GPU_DRIVER="$(printf '%s' "$query" | cut -d, -f3 | sed 's/^ *//; s/ *$//')"
    GPU_VRAM="$(printf '%s'   "$query" | cut -d, -f4 | sed 's/^ *//; s/ *$//')"
  fi

  if [ -z "$GPU_NAME" ]; then
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n 1 | sed 's/\r$//')"
    GPU_DRIVER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1 | sed 's/\r$//')"
    warn "This driver does not answer --query-gpu=compute_cap; compute capability unknown."
  fi

  if [ -z "$GPU_NAME" ]; then
    die "nvidia-smi ran but reported no GPU." \
        "Check that the card is visible to the OS and that nothing holds it exclusively."
  fi

  ok "GPU     : $GPU_NAME"
  ok "driver  : ${GPU_DRIVER:-unknown}"
  ok "compute : ${GPU_CC:-unknown}${GPU_VRAM:+   VRAM: ${GPU_VRAM} MiB}"

  # sm_120 is the interesting case: new enough that an Ollama built against an older
  # CUDA runtime has no kernel for it and falls back to the CPU. Say so now, so the
  # step 6 diagnosis is not the first the reader hears of it.
  case "$GPU_CC" in
    12.*)
      IS_BLACKWELL=1
      info "Compute capability 12.x is Blackwell (sm_120). Ollama needs to have been built"
      info "against CUDA 12.8 or newer to have a kernel for it; older builds run the model"
      info "on the CPU instead, silently. Step 6 checks for exactly that."
      ;;
  esac
}

# =============================================================================
# Step 2 - Ollama
# =============================================================================
install_ollama() {
  step "2/6  Ollama"

  if have ollama; then
    local version
    version="$(ollama --version 2>&1 | head -n 1 | sed 's/\r$//')"
    skip "Ollama already installed - ${version:-version unknown}"
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    info "Would install Ollama: curl -fsSL https://ollama.com/install.sh | sh"
    return 0
  fi

  if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
    printf '    Ollama is not installed. Install it now from https://ollama.com/install.sh? [Y/n] '
    local answer=""
    read -r answer
    case "$answer" in
      [Nn]*) die "Ollama is required and was declined." \
                 "Install it yourself, then re-run with --verify-only to check the GPU path." ;;
    esac
  fi

  have curl || die "curl is not installed, and the official Ollama installer is fetched with it." \
                   "Install curl (or install Ollama by hand from https://ollama.com/download)," \
                   "then re-run."

  info "Installing Ollama from https://ollama.com/install.sh ..."
  if ! curl -fsSL https://ollama.com/install.sh | sh; then
    die "The Ollama install script failed." \
        "Re-run it by hand to see its output:" \
        "  curl -fsSL https://ollama.com/install.sh | sh"
  fi

  ensure_ollama_on_path || die "The Ollama installer reported success but 'ollama' is still not on PATH." \
                               "Open a new shell (the installer adds /usr/local/bin) and re-run this script."

  ok "Installed Ollama - $(ollama --version 2>&1 | head -n 1)"
}

# =============================================================================
# Step 3 - venv + numpy
# =============================================================================
install_venv() {
  step "3/6  Python venv at $VENV_DIR"

  local py vpy
  if ! py="$(resolve_python)"; then
    die "No usable Python found: tried python3, then python, then py." \
        "None of them is on PATH with a version of 3.9 or newer." \
        "" \
        "Install Python 3.9+ (on Debian/Ubuntu: 'sudo apt install python3 python3-venv')" \
        "and re-run. Note that Git Bash on Windows ships without python3 - on Windows," \
        "run the PowerShell twin, bootstrap.ps1, instead."
  fi
  info "python: $py ($("$py" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null))"

  if vpy="$(venv_python)"; then
    skip "venv already exists at $VENV_DIR"
  elif [ "$DRY_RUN" -eq 1 ]; then
    info "Would create the venv: $py -m venv $VENV_DIR"
    info "Would create the index directory: $INDEX_DIR"
    info "Would pip install numpy, and -r $REQUIREMENTS if that file exists"
    info "Would pip install the localgpu CLI editable from $SCRIPT_DIR, if pyproject.toml is there"
    return 0
  else
    mkdir -p "$LOCALGPU_HOME" || die "Could not create $LOCALGPU_HOME"
    if ! "$py" -m venv "$VENV_DIR"; then
      die "'$py -m venv $VENV_DIR' failed." \
          "On Debian/Ubuntu the venv module is a separate package:" \
          "  sudo apt install python3-venv"
    fi
    vpy="$(venv_python)" || die "The venv was created but no interpreter appeared under $VENV_DIR."
    ok "Created the venv"
  fi

  run mkdir -p "$INDEX_DIR"
  [ -d "$INDEX_DIR" ] && ok "index directory: $INDEX_DIR"

  if [ "$DRY_RUN" -eq 1 ]; then
    info "Would pip install numpy, and -r $REQUIREMENTS if that file exists"
    info "Would pip install the localgpu CLI editable from $SCRIPT_DIR, if pyproject.toml is there"
    return 0
  fi

  # Detect first: whether numpy imports is the thing that actually matters, and it is a
  # cheaper and truer question than parsing pip's output.
  local numpy_version=""
  numpy_version="$("$vpy" -c 'import numpy; print(numpy.__version__)' 2>/dev/null)"

  if [ -n "$numpy_version" ] && [ ! -f "$REQUIREMENTS" ]; then
    skip "numpy already installed ($numpy_version), and there is no mcp/requirements.txt yet"
    return 0
  fi

  # pip's own idempotence is the detection for the requirements file, so compare the
  # frozen set before and after rather than trusting an exit code to mean "changed".
  local before after
  before="$("$vpy" -m pip freeze 2>/dev/null)"

  if [ -z "$numpy_version" ]; then
    info "Installing numpy into the venv ..."
    "$vpy" -m pip install --quiet --upgrade pip >/dev/null 2>&1
    if ! "$vpy" -m pip install --quiet numpy; then
      die "pip could not install numpy into $VENV_DIR." \
          "Re-run it by hand to see the error:" \
          "  $vpy -m pip install numpy"
    fi
  else
    skip "numpy already installed ($numpy_version)"
  fi

  if [ -f "$REQUIREMENTS" ]; then
    info "Installing $REQUIREMENTS ..."
    if ! "$vpy" -m pip install --quiet -r "$REQUIREMENTS"; then
      die "pip could not install $REQUIREMENTS." \
          "Re-run it by hand to see the error:" \
          "  $vpy -m pip install -r $REQUIREMENTS"
    fi
  else
    info "No mcp/requirements.txt yet - installed numpy only."
  fi

  # The `localgpu` console script, which is what `localgpu shell` resolves to.
  # EDITABLE on purpose: cli/localgpu_cli.py finds its sibling mcp/ directory
  # relative to its own __file__, and a copied install puts that __file__ in
  # site-packages, where mcp/ does not exist. Do not drop the -e.
  #
  # "Can I import it?" is not enough: an editable install from a PREVIOUS plugin
  # directory (e.g. after the plugin was reinstalled elsewhere) still imports fine -
  # it just runs the old code. Confirm the imported module's own file actually lives
  # under THIS SCRIPT_DIR before calling it installed.
  if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    if "$vpy" -c '
import os, sys
try:
    import localgpu_cli
except Exception:
    sys.exit(1)
want = os.path.realpath(os.path.join(sys.argv[1], "cli"))
got = os.path.realpath(os.path.dirname(getattr(localgpu_cli, "__file__", "") or ""))
sys.exit(0 if want == got else 1)
' "$SCRIPT_DIR" >/dev/null 2>&1; then
      skip "localgpu CLI already installed"
    else
      info "Installing the localgpu CLI (editable) ..."
      if ! "$vpy" -m pip install --quiet -e "$SCRIPT_DIR"; then
        die "pip could not install the localgpu CLI from $SCRIPT_DIR." \
            "Re-run it by hand to see the error:" \
            "  $vpy -m pip install -e $SCRIPT_DIR"
      fi
    fi
  else
    info "No pyproject.toml next to this script - skipping the localgpu CLI."
  fi

  after="$("$vpy" -m pip freeze 2>/dev/null)"
  if [ "$before" = "$after" ]; then
    skip "Python dependencies already installed - pip changed nothing"
  else
    ok "Python dependencies installed (numpy $("$vpy" -c 'import numpy; print(numpy.__version__)' 2>/dev/null))"
  fi
}

# =============================================================================
# Step 4 - models
# =============================================================================
# 'ollama list' prints NAME first, and a bare 'nomic-embed-text' is listed as
# 'nomic-embed-text:latest' - so match the tag exactly if one was asked for, and allow
# the implicit :latest otherwise.
model_present() {
  local wanted="$1" listed
  listed="$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | sed 's/\r$//')"
  [ -z "$listed" ] && return 1
  case "$wanted" in
    *:*) printf '%s\n' "$listed" | grep -qxF "$wanted" ;;
    *)   printf '%s\n' "$listed" | grep -qxF "$wanted" || printf '%s\n' "$listed" | grep -qxF "${wanted}:latest" ;;
  esac
}

pull_model() {
  local model="$1"
  if model_present "$model"; then
    skip "$model already installed"
    return 0
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    info "Would pull: ollama pull $model"
    return 0
  fi
  info "Pulling $model (a first run downloads gigabytes) ..."
  if ! ollama pull "$model"; then
    die "'ollama pull $model' failed." \
        "Check that the Ollama server is running and that this machine can reach" \
        "registry.ollama.ai, then re-run."
  fi
  ok "Pulled $model"
}

install_models() {
  step "4/6  Models"
  if [ "$SKIP_MODELS" -eq 1 ]; then
    skip "--skip-models given - not pulling $EMBED_MODEL or $CHAT_MODEL"
    return 0
  fi
  if ! have ollama; then
    if [ "$DRY_RUN" -eq 1 ]; then
      info "Would pull: ollama pull $EMBED_MODEL"
      info "Would pull: ollama pull $CHAT_MODEL"
      return 0
    fi
    die "Ollama is not on PATH, so no model can be pulled."
  fi
  pull_model "$EMBED_MODEL"
  pull_model "$CHAT_MODEL"
}

# =============================================================================
# Step 5 - VRAM discipline
# =============================================================================
# 8 GB of VRAM does not hold a 7B chat model and an embedding model at once. With more
# than one loadable, Ollama keeps the idle one resident, runs out of VRAM, and spills
# whichever it is asked for next onto the CPU - which looks exactly like the Blackwell
# fallback step 6 hunts for, and is not it. Pinning the limit to 1 removes that whole
# class of confusion.
set_vram_discipline() {
  step "5/6  VRAM discipline (OLLAMA_MAX_LOADED_MODELS=1)"

  local marker='# Added by localgpu bootstrap'
  local line='export OLLAMA_MAX_LOADED_MODELS=1'
  local wrote=0 rc

  for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
    # Only touch a profile that exists, plus .profile, which is the one every POSIX
    # login shell agrees on. Creating a .zshrc on a machine with no zsh is litter.
    if [ ! -f "$rc" ] && [ "$rc" != "$HOME/.profile" ]; then
      continue
    fi
    # Read it back first: an already-present line is the "already installed" case.
    if [ -f "$rc" ] && grep -qF "$line" "$rc" 2>/dev/null; then
      skip "OLLAMA_MAX_LOADED_MODELS=1 already exported in $rc"
      continue
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
      info "Would append '$line' to $rc"
      wrote=1
      continue
    fi
    if { printf '\n%s\n%s\n' "$marker" "$line"; } >> "$rc" 2>/dev/null; then
      ok "Exported OLLAMA_MAX_LOADED_MODELS=1 in $rc"
      wrote=1
    else
      warn "Could not write to $rc"
    fi
  done

  # A shell export only reaches an 'ollama serve' launched from a shell. The packaged
  # Linux install runs it under systemd, which inherits nothing from a profile, so it
  # needs its own drop-in. A user unit we can write; the system unit the official
  # installer creates needs root, so print the exact command rather than running sudo
  # behind the operator's back.
  local user_unit="$HOME/.config/systemd/user/ollama.service"
  local dropin_dir="$HOME/.config/systemd/user/ollama.service.d"
  local dropin="$dropin_dir/localgpu.conf"
  if have systemctl && [ -f "$user_unit" ]; then
    if [ -f "$dropin" ] && grep -qF 'OLLAMA_MAX_LOADED_MODELS=1' "$dropin" 2>/dev/null; then
      skip "systemd user drop-in already sets it: $dropin"
    elif [ "$DRY_RUN" -eq 1 ]; then
      info "Would write the systemd user drop-in: $dropin"
    else
      mkdir -p "$dropin_dir"
      printf '[Service]\nEnvironment="OLLAMA_MAX_LOADED_MODELS=1"\n' > "$dropin"
      systemctl --user daemon-reload >/dev/null 2>&1
      systemctl --user restart ollama >/dev/null 2>&1
      ok "Wrote the systemd user drop-in: $dropin"
    fi
  elif have systemctl && systemctl list-unit-files ollama.service >/dev/null 2>&1; then
    warn "Ollama runs as a system service here, which does not read your shell profile."
    note "Run this once, as root, or the setting never reaches the server:"
    note "  sudo systemctl edit ollama    # then add:"
    note "  [Service]"
    note '  Environment="OLLAMA_MAX_LOADED_MODELS=1"'
    note "  sudo systemctl restart ollama"
  fi

  # Whatever the persistence story, this process and step 6 need it now.
  export OLLAMA_MAX_LOADED_MODELS=1
  if [ "$wrote" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    info "Nothing to change - the setting is already persistent."
  fi

  info "keep_alive: the MCP client sends a short keep_alive on every request - seconds for"
  info "an embedding call, minutes at most for a chat call - instead of Ollama's 5m default,"
  info "so a model it has finished with releases its VRAM rather than squatting on it. That"
  info "is what lets one 8 GB card serve both an embedding model and a 7B chat model;"
  info "OLLAMA_MAX_LOADED_MODELS=1 is the backstop for when it does not."
}

# =============================================================================
# Step 6 - VERIFY
# =============================================================================
ollama_up() { http_get "$OLLAMA_URL/api/version" 3 >/dev/null 2>&1; }

ensure_ollama_running() {
  ollama_up && return 0
  info "Ollama is not answering on $OLLAMA_URL - starting it ..."
  nohup ollama serve >/dev/null 2>&1 &
  local i=0
  while [ "$i" -lt 15 ]; do
    sleep 2
    if ollama_up; then ok "Ollama server is up"; return 0; fi
    i=$((i + 1))
  done
  return 1
}

# Count the floats in an embed response. Prefer a real JSON parse with whichever Python
# we can find (the venv's, ideally); if there is none, say the dimension is unknown
# rather than pretending we checked more than we did.
embed_dimension() {
  local body="$1" py=""
  py="$(venv_python 2>/dev/null)" || py="$(resolve_python 2>/dev/null)" || py=""
  [ -z "$py" ] && return 1
  printf '%s' "$body" | "$py" -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
vector = payload.get("embeddings") or payload.get("embedding")
if isinstance(vector, list) and vector and isinstance(vector[0], list):
    vector = vector[0]
if not isinstance(vector, list) or not vector:
    raise SystemExit(1)
if not all(isinstance(x, (int, float)) for x in vector):
    raise SystemExit(1)
print(len(vector))
' 2>/dev/null
}

# The PROCESSOR column of the 'ollama ps' row for this model, or "" if it has no row.
processor_row() {
  local model="$1" base
  base="${model%%:*}"
  ollama ps 2>/dev/null | tail -n +2 | sed 's/\r$//' | grep -F "$base" | head -n 1
}

# The whole reason this script exists. Never returns on a GPU failure.
assert_on_gpu() {
  local model="$1" label="$2" ps_out row
  ps_out="$(ollama ps 2>&1 | sed 's/\r$//')"
  row="$(processor_row "$model")"

  if [ -z "$row" ]; then
    die "$label ran, but 'ollama ps' does not list $model as resident." \
        "The request was sent with an explicit 60s keep_alive, so the model should still" \
        "have been loaded when we looked. A model that is gone this fast means the server" \
        "evicted it immediately - which on this hardware means it could not fit, or could" \
        "not run, on the GPU." \
        "" \
        "Verbatim 'ollama ps' output:" \
        "$ps_out"
  fi

  # PROCESSOR reads '100% GPU', '100% CPU', or a split like '38%/62% CPU/GPU'. Any
  # mention of CPU at all is an offload, and an offload is a failure here: a partial one
  # is still the slow path, and on 8 GB it is usually the prelude to a full one.
  #
  # The *CPU* arm MUST stay above the *GPU* arm. A split row contains both words, so
  # testing for GPU first reports '38%/62% CPU/GPU' as a pass - a green tick on the
  # exact condition this function exists to catch. Do not reorder these.
  case "$row" in
    *CPU*)
      local arch_note="This GPU reports compute capability ${GPU_CC:-unknown}."
      if [ "$IS_BLACKWELL" -eq 1 ]; then
        arch_note="This is a Blackwell card (compute capability $GPU_CC, sm_120)."
      fi
      # Built up rather than inlined as "${GPU_VRAM:-this card's VRAM}": bash treats an
      # apostrophe inside a ${x:-word} default as an opening quote even within double
      # quotes, and the parser then runs on to the next ' hundreds of lines below.
      local vram_note="this card's VRAM"
      if [ -n "$GPU_VRAM" ]; then
        vram_note="$GPU_VRAM MiB"
      fi
      die "$label is running on the CPU, not the GPU." \
          "$arch_note Ollama only has a kernel for sm_120 if it was built against CUDA" \
          "12.8 or newer. An older build finds no usable kernel, says nothing about it," \
          "and quietly runs the model on the CPU instead - roughly an order of magnitude" \
          "slower, and not what localgpu is for." \
          "" \
          "Verbatim 'ollama ps' output:" \
          "$ps_out" \
          "" \
          "What to do:" \
          "  1. Update Ollama to the newest release, then re-run with --verify-only:" \
          "       curl -fsSL https://ollama.com/install.sh | sh" \
          "  2. If it still offloads, check that nothing else is holding the VRAM:" \
          "       nvidia-smi" \
          "  3. A partial split ('38%/62% CPU/GPU') with a clean nvidia-smi means the model" \
          "     does not fit in $vram_note - use a smaller quantisation."
      ;;
    *GPU*)
      ok "$label is on the GPU - $row"
      ;;
    *)
      die "$label: could not read a PROCESSOR column out of 'ollama ps'." \
          "This script refuses to report a pass it did not actually observe." \
          "" \
          "Verbatim 'ollama ps' output:" \
          "$ps_out"
      ;;
  esac
}

verify() {
  step "6/6  VERIFY - a real request, on the GPU"

  if [ "$DRY_RUN" -eq 1 ]; then
    info "Would POST an embed request for $EMBED_MODEL to $OLLAMA_URL/api/embed"
    info "Would then require 'ollama ps' to show it on GPU with no CPU offload"
    if [ "$SKIP_MODELS" -eq 0 ]; then
      info "Would do the same for $CHAT_MODEL via $OLLAMA_URL/api/generate"
    fi
    return 0
  fi

  have ollama || die "Ollama is not on PATH, so nothing can be verified."
  ensure_ollama_running || die "Ollama is not answering on $OLLAMA_URL after 30 seconds." \
    "Start it by hand ('ollama serve') and re-run with --verify-only."

  # --- the embedding model ---
  info "Embedding a test string with $EMBED_MODEL ..."
  local body dim
  # /api/embed is the current endpoint; /api/embeddings is the older one, still served.
  # Try the new one and fall back, so this works either side of that change.
  body="$(http_post "$OLLAMA_URL/api/embed" \
    "{\"model\":\"$EMBED_MODEL\",\"input\":\"localgpu bootstrap verification\",\"keep_alive\":\"60s\"}" 180)"
  if [ -z "$body" ]; then
    body="$(http_post "$OLLAMA_URL/api/embeddings" \
      "{\"model\":\"$EMBED_MODEL\",\"prompt\":\"localgpu bootstrap verification\",\"keep_alive\":\"60s\"}" 180)"
  fi
  if [ -z "$body" ]; then
    die "The embed request to $OLLAMA_URL returned nothing." \
        "Reproduce it by hand:" \
        "  curl -s $OLLAMA_URL/api/embed -d '{\"model\":\"$EMBED_MODEL\",\"input\":\"hi\"}'"
  fi
  case "$body" in
    *'"error"'*) die "Ollama rejected the embed request." "Its reply, verbatim:" "$body" ;;
  esac

  if dim="$(embed_dimension "$body")" && [ -n "$dim" ]; then
    ok "Embedded - $EMBED_MODEL returned $dim dimensions"
  else
    case "$body" in
      *'"embedding'*) warn "Got an embedding back, but no JSON parser was available to count its dimensions." ;;
      *) die "The embed reply contained no embedding." "Its reply, verbatim:" "$body" ;;
    esac
  fi

  assert_on_gpu "$EMBED_MODEL" "$EMBED_MODEL"

  # --- the chat model ---
  # Verifying only the 137M embedding model would be a false green: something that small
  # runs anywhere. The 7B chat model at q4_K_M is the one that has to fit and has to find
  # an sm_120 kernel, so it is the one worth asking.
  if [ "$SKIP_MODELS" -eq 1 ]; then
    skip "--skip-models given - not loading $CHAT_MODEL to check its placement"
  else
    info "Generating one token with $CHAT_MODEL (loads ~5 GB, give it a minute) ..."
    body="$(http_post "$OLLAMA_URL/api/generate" \
      "{\"model\":\"$CHAT_MODEL\",\"prompt\":\"ok\",\"stream\":false,\"options\":{\"num_predict\":1},\"keep_alive\":\"60s\"}" 600)"
    if [ -z "$body" ]; then
      die "The generate request for $CHAT_MODEL returned nothing." \
          "Reproduce it by hand:" \
          "  curl -s $OLLAMA_URL/api/generate -d '{\"model\":\"$CHAT_MODEL\",\"prompt\":\"ok\",\"stream\":false}'"
    fi
    case "$body" in
      *'"error"'*) die "Ollama rejected the generate request for $CHAT_MODEL." "Its reply, verbatim:" "$body" ;;
    esac
    ok "$CHAT_MODEL answered"
    assert_on_gpu "$CHAT_MODEL" "$CHAT_MODEL"
  fi

  printf '\n\033[32mVerified: every model checked loads on the GPU with no CPU offload.\033[0m\n'
}

# =============================================================================
# Run
# =============================================================================
# Step 1 always runs: it only reads, and step 6's diagnosis needs its answers.
check_driver

# Before anything asks "is Ollama installed?" - steps 2, 4 and 6 all do, and --verify-only
# skips step 2 entirely, so this has to happen here rather than inside any one of them.
ensure_ollama_on_path || :

if [ "$VERIFY_ONLY" -eq 1 ]; then
  skip "--verify-only given - skipping steps 2-5"
  verify
else
  install_ollama
  install_venv
  ensure_localgpu_on_path
  install_models
  set_vram_discipline
  verify
fi

step "Done"
ok "install root : $LOCALGPU_HOME"
ok "venv         : $VENV_DIR"
ok "index        : $INDEX_DIR"
ok "models       : $EMBED_MODEL, $CHAT_MODEL"
if [ "$DRY_RUN" -eq 1 ]; then
  info "This was a --dry-run. Nothing was installed, written, or verified."
else
  info "Re-run any time; every step above detects before it acts."
  info "To re-check the GPU path alone: ./bootstrap.sh --verify-only"
  if [ "$VERIFY_ONLY" -eq 0 ]; then
    info ""
    info "IMPORTANT: this shell does not see the PATH change above - open a NEW shell"
    info "before 'localgpu' will resolve there."
  fi
fi
