#!/usr/bin/env bash
# _verify/run-all.sh - the deep suite. Everything smoke.sh is too slow to carry.
# Exit 0 = every runnable check passed. Minutes, not seconds.
#
# Budget reality on this machine (Windows + Git Bash, where process spawn is
# expensive): check-marketplace.py ~163s, menu-groups.sh ~171s. Neither fits the
# 90s smoke budget, and both are real. This is where they live.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
echo "RUN-ALL target: $(pwd) @ ${SHA}"
echo

WITH_HOOKS=0
for a in "$@"; do [ "$a" = "--with-hooks" ] && WITH_HOOKS=1; done

PY=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "FATAL: no python3/python/py on PATH" >&2; exit 1; }

PWSH="C:/Program Files/PowerShell/7/pwsh.exe"
[ -x "$PWSH" ] || PWSH="$(command -v pwsh 2>/dev/null || true)"

PASS=0; FAIL=0; SKIP=0
run() {
  local n="$1" t="$2"; shift 2
  echo "--- $n"
  local s e
  s=$(date +%s)
  if timeout "$t" "$@"; then e=$(date +%s); echo "    PASS ($((e-s))s)"; PASS=$((PASS+1))
  else
    local rc=$?; e=$(date +%s)
    [ "$rc" -eq 124 ] && echo "    FAIL: TIMED OUT after ${t}s" || echo "    FAIL (exit $rc, $((e-s))s)"
    FAIL=$((FAIL+1))
  fi
}
skip() { echo "--- $1"; echo "    SKIP: $2"; SKIP=$((SKIP+1)); }

# 1. Everything smoke checks, PLUS the version-drift walk it cannot afford.
#    That walk is the one check no amount of reading the tree can replace: it
#    compares each plugin's files against the commit where its version was last
#    set. A missed bump looks fine here and is permanently broken for anyone who
#    already installed the plugin.
run "marketplace: full gate, including version drift" 400 "$PY" scripts/check-marketplace.py

# 2. The install-script menu contract end to end.
run "install scripts: sub-picker catalogs, group flags, parent implication" 400 \
    bash scripts/_test/menu-groups.sh

# 3. localgpu's own suite, on the venv that owns numpy (system python has none).
#    Root resolution matches _verify/smoke.sh's localgpu_cli_check: $LOCALGPU_HOME
#    first, else the platform defaults ($HOME/.local/share/localgpu on POSIX,
#    $LOCALAPPDATA/localgpu on Windows). LOCALAPPDATA is unset on POSIX, so it must
#    stay behind a ${...:-} guard under `set -u` rather than being read unconditionally.
VENV_PY=""
localgpu_candidates=()
if [ -n "${LOCALGPU_HOME:-}" ]; then
  localgpu_candidates+=("$LOCALGPU_HOME")
else
  localgpu_candidates+=("$HOME/.local/share/localgpu")
  [ -n "${LOCALAPPDATA:-}" ] && localgpu_candidates+=("$LOCALAPPDATA/localgpu")
fi
for localgpu_root in "${localgpu_candidates[@]}"; do
  if [ -x "$localgpu_root/venv/bin/python" ]; then
    VENV_PY="$localgpu_root/venv/bin/python"; break
  elif [ -x "$localgpu_root/venv/Scripts/python.exe" ]; then
    VENV_PY="$localgpu_root/venv/Scripts/python.exe"; break
  fi
done
if [ -n "$VENV_PY" ] && [ -d plugin/localgpu/mcp/_test ]; then
  run "localgpu: engine unit tests" 300 "$VENV_PY" -m pytest plugin/localgpu/mcp/_test -q
else
  skip "localgpu: engine unit tests" "venv or _test/ missing - run /localgpu:setup"
fi

# 4. The audit's label()/canon() contract.
run "crew-setup: CLAUDE.md heading round-trip" 60 \
    bash plugin/crew/skills/crew-setup/scripts/_test/round-trip.sh

# 5. Every PowerShell artifact, tracked and untracked. See smoke.sh for why the
#    untracked ones are checked one at a time (param([string]$Path) takes ONE path).
if [ -n "$PWSH" ]; then
  run "powershell: tracked (CI mode)" 120 "$PWSH" -NoProfile -File scripts/check-powershell.ps1
  # Process-substitution redirect, not a pipe: `git ls-files | while read` runs the
  # loop body in a subshell, so a failure `run` records inside it (PASS/FAIL are
  # incremented in the subshell's copy) never reaches the parent shell and run-all
  # exits 0 over a check it actually observed failing. `< <(...)` keeps the loop in
  # this shell.
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    run "powershell: untracked $f" 60 "$PWSH" -NoProfile -File scripts/check-powershell.ps1 -Path "$f"
  done < <(git ls-files -o --exclude-standard '*.ps1' '*.psm1')
else
  skip "powershell" "pwsh not found"
fi

# 6. QUARANTINED - crew's blocking-guard suite HANGS on this platform.
#    It prints "== guard.sh: must BLOCK (exit 2) ==", emits
#    `OSError: [Errno 22] Invalid argument` flushing sys.stdout, and never
#    returns. Closing stdin does not help. See .work/SMOKE-GAPS.md.
#    It is NOT skipped because it is unimportant - it is the only thing proving a
#    blocking guard still blocks. It is skipped because a hanging check in a gate
#    is worse than an absent one: it stalls every run instead of failing.
if [ "$WITH_HOOKS" -eq 1 ]; then
  run "crew hooks: blocking-guard regression suite" 240 \
      bash plugin/crew/hooks/scripts/_test/run-tests.sh
else
  skip "crew hooks: blocking-guard regression suite" \
       "hangs on Windows/Git Bash - see .work/SMOKE-GAPS.md; force with --with-hooks"
fi

# 7. Never automatic: drives the real Claude Code CLI, which no runner has.
skip "plugin update path: drift-detection.sh" \
     "needs the real claude CLI - run by hand before pushing a plugin-update change"

echo
echo "run-all: $PASS passed, $FAIL failed, $SKIP skipped"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
