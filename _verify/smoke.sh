#!/usr/bin/env bash
# _verify/smoke.sh - fast and shallow. Exit 0 = safe to merge/promote, 1 = stop.
# 9 checks, target is under 90 seconds. Depth belongs in run-all.sh.
#
# This repo is a Claude Code marketplace: there is no service to curl and no
# environment to deploy to. "Smoke" here means the registration invariants hold
# and every executable artifact still parses - the things that are broken for
# *other people* rather than in this working tree.
#
# It does NOT reimplement scripts/check-marketplace.py. It imports that module
# and calls the same check functions main() does, minus check_versions - the
# version-drift walk reads 58 revisions of marketplace.json and runs a git diff
# per entry, which costs ~160s on its own. That check is real and it runs in
# run-all.sh; putting it here would blow the budget and get the suite skipped,
# which is how a gate stops meaning anything.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

# Resolve the target and SAY IT. A suite that passes against the wrong tree is
# the most convincing wrong answer available.
SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
DIRTY="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
echo "SMOKE target: $(pwd) @ ${SHA} (${DIRTY} uncommitted change(s))"
echo

PASS=0; FAIL=0
check() {
  local n="$1"; shift
  if "$@" >/tmp/_smoke.$$ 2>&1; then
    echo "PASS $n"; PASS=$((PASS+1))
  else
    echo "FAIL $n"; sed 's/^/       /' /tmp/_smoke.$$ | head -12; FAIL=$((FAIL+1))
  fi
  rm -f /tmp/_smoke.$$
}

# python3 is not guaranteed: Git Bash ships without it. Resolve and fail loudly
# rather than letting every python check report as a broken check.
PY=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
if [ -z "$PY" ]; then
  echo "FATAL: no python3/python/py on PATH - cannot run the registration checks" >&2
  exit 1
fi

# pwsh is NOT on Git Bash's PATH on the maintainer's machine. Named absolutely,
# then verified: a bare `pwsh` fails as "command not found" and the gate reports
# that as a FAILED CHECK rather than a missing tool.
PWSH="C:/Program Files/PowerShell/7/pwsh.exe"
[ -x "$PWSH" ] || PWSH="$(command -v pwsh 2>/dev/null || true)"

# --- checks 1-6: the registration invariants, from the real implementation ----
run_marketplace_check() {
  "$PY" - "$1" <<'PY'
import importlib.util, pathlib, sys
which = sys.argv[1]
spec = importlib.util.spec_from_file_location("cm", pathlib.Path("scripts/check-marketplace.py"))
cm = importlib.util.module_from_spec(spec); spec.loader.exec_module(cm)

entries, disk, problems = cm.load_entries(), cm.on_disk(), []
fail = problems.append

# Same calls main() makes, in the same order, minus check_versions (slow: see header).
groups = {
    "registration": lambda: cm.check_registration(entries, disk, fail),
    "skills":       lambda: cm.check_skill_manifests(entries, fail),
    "plugins":      lambda: cm.check_plugin_manifests(entries, fail),
    "catalogs":     lambda: (cm.check_catalogs(entries, fail), cm.check_docs(entries, fail)),
    "menus":        lambda: (cm.check_menu_parity(fail), cm.check_group_parity(fail)),
    "hooks":        lambda: cm.check_hook_commands(entries, fail),
}
if which not in groups:
    print(f"unknown check group: {which}"); sys.exit(1)
groups[which]()
for p in problems:
    print(p)
sys.exit(1 if problems else 0)
PY
}

check "registration: every dir registered, every source resolves, no nested marketplace" \
      run_marketplace_check registration
check "skill manifests: SKILL.md present, frontmatter name matches its directory" \
      run_marketplace_check skills
check "plugin manifests: plugin.json version agrees with marketplace.json" \
      run_marketplace_check plugins
check "catalogs: every entry has its row in all three README tables" \
      run_marketplace_check catalogs
check "install scripts: .sh and .ps1 menus are a matched pair" \
      run_marketplace_check menus
check "hook commands: \${CLAUDE_PLUGIN_ROOT} quoted, PowerShell ends with ; exit \$LASTEXITCODE" \
      run_marketplace_check hooks

# --- check 7: every PowerShell artifact still parses -------------------------
# CI mode enumerates via `git ls-files`, so an UNTRACKED .ps1 is invisible to it.
# That is how plugin/localgpu/bootstrap.ps1 passed a gate that never opened it.
# Pass the tracked-and-untracked union explicitly so new files are covered.
ps_check() {
  [ -n "$PWSH" ] || { echo "pwsh not found - install it or drop this check"; return 1; }
  local rc=0 untracked n

  # check-powershell.ps1 declares `param([string]$Path)` - ONE string, not an array.
  # Passing a list binds only the first path and silently drops the rest, which makes
  # this check pass while opening a single file. Found by sabotage: breaking an
  # untracked .ps1 left the check green. So: CI mode once for everything tracked,
  # then one invocation per untracked file (normally none).
  "$PWSH" -NoProfile -File scripts/check-powershell.ps1 || rc=1

  untracked="$(git ls-files -o --exclude-standard '*.ps1' '*.psm1')"
  n=0
  if [ -n "$untracked" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      n=$((n+1))
      "$PWSH" -NoProfile -File scripts/check-powershell.ps1 -Path "$f" || rc=1
    done <<EOF
$untracked
EOF
  fi
  echo "(tracked: CI mode; untracked checked individually: $n)"
  return $rc
}
check "powershell: every .ps1 parses and every Verb-Noun call resolves (incl. untracked)" ps_check

# --- check 8: the audit's own label()/canon() contract -----------------------
check "crew-setup: every recommended CLAUDE.md heading round-trips through canon()" \
      bash plugin/crew/skills/crew-setup/scripts/_test/round-trip.sh

# --- check 9: the localgpu console script is on the PERSISTENT PATH ----------
# T-0001: 'pip install -e' puts a working console script in the venv's script dir, but
# nothing before bootstrap.sh's/bootstrap.ps1's PATH step made that dir persistent on
# PATH. This checks the PERSISTED record - a profile file on POSIX, the Windows
# User-scope registry value on Windows - rather than 'command -v localgpu'. A shell that
# was already running when bootstrap persisted the entry never re-reads either of those
# on its own (the exact fact ensure_ollama_on_path/Resolve-OllamaOnPath above are built
# around), so testing the live shell's PATH here would fail on a machine bootstrap fixed
# correctly, in precisely the shell most likely to be running this check right after it.
# Only meaningful on a machine where localgpu has actually been bootstrapped - on a
# fresh checkout (CI included) there is no venv yet, so this passes trivially.
localgpu_cli_check() {
  local candidates=()
  if [ -n "${LOCALGPU_HOME:-}" ]; then
    candidates+=("$LOCALGPU_HOME")
  else
    candidates+=("$HOME/.local/share/localgpu")
    if [ -n "${LOCALAPPDATA:-}" ]; then
      if command -v cygpath >/dev/null 2>&1; then
        candidates+=("$(cygpath -u "$LOCALAPPDATA")/localgpu")
      else
        candidates+=("$LOCALAPPDATA/localgpu")
      fi
    fi
  fi

  # Is $1 (a POSIX-shaped path) in the Windows User-scope registry PATH bootstrap.ps1
  # writes to? Only meaningful where pwsh is here; a POSIX-only box has no such registry
  # and this just reports "no" without touching anything.
  registry_has_dir() {
    [ -n "$PWSH" ] || return 1
    local win_dir="$1"
    if command -v cygpath >/dev/null 2>&1; then
      win_dir="$(cygpath -w "$1" 2>/dev/null)" || win_dir="$1"
    fi
    TARGET_DIR="$win_dir" "$PWSH" -NoProfile -Command '
      $dirs = [Environment]::GetEnvironmentVariable("Path","User") -split ";" | Where-Object { $_ }
      if ($dirs -contains $env:TARGET_DIR) { exit 0 } else { exit 1 }
    ' >/dev/null 2>&1
  }

  local home venv scripts_dir script found=0
  local found_roots=()
  for home in "${candidates[@]}"; do
    venv="$home/venv"
    [ -d "$venv" ] || continue
    found=1
    found_roots+=("$home")

    if [ -x "$venv/bin/python" ]; then
      scripts_dir="$venv/bin"
    elif [ -x "$venv/Scripts/python.exe" ]; then
      scripts_dir="$venv/Scripts"
    else
      echo "venv exists at $venv but has no interpreter under bin/ or Scripts/"
      return 1
    fi

    if [ -x "$scripts_dir/localgpu" ]; then
      script="$scripts_dir/localgpu"
    elif [ -x "$scripts_dir/localgpu.exe" ]; then
      script="$scripts_dir/localgpu.exe"
    else
      echo "no localgpu console script under $scripts_dir - was 'pip install -e' run?"
      return 1
    fi
    echo "found: $script"

    local in_profile=0 rc
    for rc in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
      [ -f "$rc" ] || continue
      grep -qF "$scripts_dir" "$rc" 2>/dev/null && in_profile=1
    done

    local in_registry=0
    registry_has_dir "$scripts_dir" && in_registry=1

    if [ "$in_profile" -eq 0 ] && [ "$in_registry" -eq 0 ]; then
      echo "$scripts_dir is not on the PERSISTENT PATH (checked profile files and the User registry)"
      echo "expected it there via bootstrap.sh's ensure_localgpu_on_path / bootstrap.ps1's Add-LocalGpuVenvToPath"
      return 1
    fi
    echo "persisted on PATH: $scripts_dir"

    if command -v localgpu >/dev/null 2>&1; then
      echo "  (and resolves in this shell already)"
    else
      echo "  (not visible in THIS shell yet - that's expected until a new one is opened)"
    fi
  done

  if [ "$found" -eq 0 ]; then
    echo "no localgpu venv under: ${candidates[*]} - not bootstrapped on this machine, nothing to check"
  fi

  # T-0002: this loop used to search BOTH candidate roots and pass as soon as EITHER
  # was persisted on PATH - which is exactly how this check went 9/9 green on a machine
  # that had a venv at BOTH roots at once (bootstrap.sh and bootstrap.ps1 disagreeing on
  # the default). Widening the search to be robust also made it blind to duplication;
  # a venv at more than one root is a FAIL regardless of what each one's PATH state is.
  if [ "${#found_roots[@]}" -gt 1 ]; then
    echo "a venv exists at MORE THAN ONE install root: ${found_roots[*]}"
    echo "that is the split T-0002 fixed - two venvs, two 'localgpu' binaries, and which"
    echo "one runs depends on which shell you're in. Remove the stray root (bootstrap.sh"
    echo "and bootstrap.ps1 both name the canonical one when they detect this) and re-run."
    return 1
  fi
  return 0
}
check "localgpu CLI: console script is on the persistent PATH (skips if not bootstrapped here)" \
      localgpu_cli_check

# --- check 10: every copy of a plugin's version agrees, Python source included -
# check-marketplace.py enforces plugin.json == marketplace.json. It knows nothing
# about pyproject.toml, so a plugin that also ships a Python package carries a
# third version that nothing compared - and localgpu drifted to 0.1.0 against
# 0.1.2 in both manifests within a day of being created. Worse: two MORE copies
# lived as hardcoded string literals in Python source (mcp/server.py's VERSION,
# cli/localgpu_cli.py's __version__) that this check didn't see either, so
# `localgpu --version` kept reporting 0.1.0 four bumps after the manifests had
# moved to 0.1.4 - the same class of failure as a missed bump: correct locally,
# wrong on the installed machine. Generic over plugins, not hardcoded to
# localgpu - the next one to grow a Python package is covered for free, in
# whichever of the two styles below it uses:
#   - a literal `VERSION = "x"` / `__version__ = "x"` assignment anywhere under
#     the plugin dir (excluding tests/build artifacts) - compared by regex, no
#     import needed;
#   - a `_version.py` module that DERIVES the value (e.g. by reading
#     pyproject.toml itself, as localgpu's now does) - executed in isolation
#     and its result compared, so a bug in the derivation itself is caught too,
#     not just a stale literal.
version_agreement_check() {
  "$PY" - <<'PY'
import importlib.util, json, pathlib, re, sys

mp = {e["name"]: e["version"]
      for e in json.loads(pathlib.Path(".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["plugins"]}
problems = []

LITERAL_RE = re.compile(r'^\s*(?:VERSION|__version__)\s*=\s*"([^"]+)"', re.MULTILINE)
SKIP_DIR_NAMES = {"_test", "__pycache__", "node_modules", "venv", ".venv", "build", "dist"}


def is_skipped(path: pathlib.Path) -> bool:
    return any(part in SKIP_DIR_NAMES or part.endswith(".egg-info") for part in path.parts)


for pyproj in sorted(pathlib.Path("plugin").glob("*/pyproject.toml")):
    plugin_dir = pyproj.parent
    name = plugin_dir.name
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', pyproj.read_text(encoding="utf-8"), re.M)
    if not m:
        problems.append(f"{name}: pyproject.toml has no version field"); continue
    py = m.group(1)
    pj_path = plugin_dir / ".claude-plugin" / "plugin.json"
    pj = json.loads(pj_path.read_text(encoding="utf-8")).get("version") if pj_path.exists() else None
    want = mp.get(name)
    if want is None:
        problems.append(f"{name}: has a pyproject.toml but no marketplace entry"); continue
    if py != want or (pj is not None and pj != want):
        problems.append(
            f"{name}: version disagreement - pyproject.toml={py} plugin.json={pj} marketplace.json={want}")

    for pyfile in sorted(plugin_dir.rglob("*.py")):
        if is_skipped(pyfile):
            continue
        for literal in LITERAL_RE.findall(pyfile.read_text(encoding="utf-8")):
            if literal != want:
                problems.append(
                    f"{name}: {pyfile} hardcodes version {literal!r}, marketplace.json wants {want!r}")

    for version_module in sorted(plugin_dir.rglob("_version.py")):
        if is_skipped(version_module):
            continue
        spec = importlib.util.spec_from_file_location("_localgpu_smoke_version", version_module)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            derived = getattr(mod, "VERSION", None)
        except Exception as exc:  # noqa: BLE001 - report, don't crash the check
            problems.append(f"{name}: {version_module} failed to import - {exc}")
            continue
        if derived != want:
            problems.append(
                f"{name}: {version_module} resolves to {derived!r}, marketplace.json wants {want!r}")

for p in problems:
    print(p)
sys.exit(1 if problems else 0)
PY
}
check "versions: pyproject.toml, plugin.json, marketplace.json and every Python-source copy agree" \
      version_agreement_check

echo
echo "smoke: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
