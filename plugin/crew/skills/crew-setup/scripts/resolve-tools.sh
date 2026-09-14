#!/usr/bin/env bash
#
# Resolve how to invoke each tool this repo's checks depend on, on THIS machine.
#
# platform.sh reports what you are running on. This answers the question that
# actually blocks work: the map says `terraform validate`, but is terraform on
# this shell's PATH, is it only inside WSL, or is it nowhere?
#
# Resolve once, at setup, and write the resolved command into .crew/verify.json.
# Do NOT branch at runtime: a check that means something different depending on
# which shell launched it is a check nobody can reason about.
#
# Usage:
#   bash resolve-tools.sh                 # tools named in .crew/verify.json
#   bash resolve-tools.sh terraform tflint ruff
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 1

PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || command -v py 2>/dev/null) || PY=""

TOOLS="$*"
if [ -z "$TOOLS" ]; then
  if [ -f .crew/verify.json ] && [ -n "$PY" ]; then
    # First bare word of every command in every `run` / environment list.
    #
    # stderr is NOT redirected to /dev/null here any more. It used to be, and
    # that is what turned an unreadable map into "nothing to resolve": the
    # named refusal below would have gone to the same place as a traceback.
    TOOLS=$("$PY" - <<'PY'
import json, os, re, shlex, sys
seen, out = set(), []
try: cfg = json.load(open(".crew/verify.json"))
except Exception: raise SystemExit

# A command is ONE LINE. The same rule verify-gate.sh enforces, for the same
# map, refused in the same words -- the three readers of `run` have to agree,
# or setup writes a verify.json the gate then refuses at the end of a turn.
# Here the symptom was different and just as quiet: `scan` splits on shell
# operators, not on newlines, so a multi-line entry was tokenised into junk
# tool names and reported as MISSING TOOLS -- names nobody wrote, next to real
# ones, in the table a user copies into verify.json.
FRAMING = {"\n": "a newline", "\r": "a carriage return",
           "\x1d": "an ASCII group separator (0x1d)",
           "\x1e": "an ASCII record separator (0x1e)"}

def reject_unrepresentable(where, entries):
    if not isinstance(entries, list):
        return
    for i, c in enumerate(entries):
        if not isinstance(c, str):
            continue
        for ch, name in FRAMING.items():
            if ch in c:
                head = c.split(ch, 1)[0].strip()[:60]
                print(f"PARSE_ERROR: .crew/verify.json {where}[{i}] contains "
                      f"{name}, so crew cannot represent it as one command. "
                      f"The entry begins: {head!r}. Split it into separate "
                      f"entries, or move it into a script and call that.",
                      file=sys.stderr)
                sys.exit(4)

for ri, rule in enumerate(cfg.get("rules", []) or []):
    if isinstance(rule, dict):
        reject_unrepresentable(f"rules[{ri}].run", rule.get("run"))
reject_unrepresentable("always", cfg.get("always"))
reject_unrepresentable("default", cfg.get("default"))
for env_name, env in (cfg.get("environments", {}) or {}).items():
    if isinstance(env, dict):
        for key in ("deploy", "smoke", "regression", "verify"):
            reject_unrepresentable(f"environments[{env_name!r}].{key}",
                                   env.get(key))

cmds = []
for r in cfg.get("rules", []): cmds += r.get("run", [])
cmds += cfg.get("always", []) + cfg.get("default", [])
for e in cfg.get("environments", {}).values():
    for k in ("deploy", "smoke", "regression", "verify"): cmds += e.get(k, [])

# `bash some/script.sh` (or `sh`) resolves only "bash" itself, which tells you
# nothing about what the script calls. Look inside it too, so a rule that
# reads `["bash ./_verify/smoke.sh"]` still surfaces terraform, ruff, psql,
# whatever the script actually shells out to.
scripts_seen = set()

def scan(cmd_str):
    for part in re.split(r'&&|\|\||[|;]', cmd_str):
        part = part.strip()
        if not part: continue
        try: toks = shlex.split(part)
        except ValueError: toks = part.split()
        if not toks: continue
        word = toks[0]
        if word in ("bash", "sh"):
            script = next((t for t in toks[1:] if not t.startswith("-")), None)
            if script and script not in scripts_seen and os.path.isfile(script):
                scripts_seen.add(script)
                try:
                    with open(script, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            line = line.split("#", 1)[0].strip()
                            if line: scan(line)
                except OSError:
                    pass
            continue
        if word.startswith(("./", "/", "$")) or "=" in word: continue
        if word in ("true", "false", "echo", "cd", "npx"): continue
        if word not in seen:
            seen.add(word); out.append(word)

for c in cmds:
    scan(c)
print(" ".join(out))
PY
)
    PY_STATUS=$?
    # Exit 4 is the ONLY status meaning "the map names a command crew cannot
    # represent"; the PARSE_ERROR above says which entry. Fail closed rather
    # than print a tool table derived from junk tokens - the table is what a
    # user pastes back into verify.json, so a wrong row here becomes a wrong
    # rule there. Any other non-zero status leaves TOOLS empty and falls
    # through to the "nothing to resolve" exit below, unchanged.
    if [ "$PY_STATUS" -eq 4 ]; then
      echo "resolve-tools: refusing to resolve tools from .crew/verify.json - it names a command crew cannot represent (see the PARSE_ERROR above). Fix that entry first; verify-gate.sh refuses the same map." >&2
      exit 2
    fi
  fi
fi
[ -z "$TOOLS" ] && { echo "resolve-tools: nothing to resolve (no args and no .crew/verify.json)" >&2; exit 0; }

# Is WSL reachable from here, and which distro answers?
WSL_OK=0
WSL_DISTRO=""
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*)
    if command -v wsl.exe >/dev/null 2>&1 && wsl.exe -e true >/dev/null 2>&1; then
      WSL_OK=1
      WSL_DISTRO=$(wsl.exe -e sh -c 'echo "$WSL_DISTRO_NAME"' 2>/dev/null | tr -d '\r')
      [ -z "$WSL_DISTRO" ] && WSL_DISTRO="default"
    fi
    ;;
esac

printf '%-18s %-10s %s\n' "TOOL" "WHERE" "USE THIS IN verify.json"
printf '%-18s %-10s %s\n' "----" "-----" "-----------------------"

MISSING=""
WRAPPED=""
for t in $TOOLS; do
  if command -v "$t" >/dev/null 2>&1; then
    printf '%-18s %-10s %s\n' "$t" "native" "$t"
  elif [ "$WSL_OK" -eq 1 ] && wsl.exe -e sh -lc "command -v $t" >/dev/null 2>&1; then
    printf '%-18s %-10s %s\n' "$t" "wsl only" "wsl.exe -e $t"
    WRAPPED="$WRAPPED $t"
  else
    printf '%-18s %-10s %s\n' "$t" "MISSING" "install it, or remove the rule that needs it"
    MISSING="$MISSING $t"
  fi
done

echo
[ "$WSL_OK" -eq 1 ] && echo "WSL reachable (distro: $WSL_DISTRO)" || echo "WSL not reachable from this shell"

if [ -n "$WRAPPED" ]; then
  cat <<TXT

WSL-ONLY TOOLS:$WRAPPED

Write the wrapped form into .crew/verify.json - do not leave the bare name and
hope. A bare \`terraform validate\` in a rule, on a machine where terraform lives
only inside WSL, fails with "command not found", and the gate reports that as a
FAILED CHECK rather than as a missing tool. You then spend an afternoon on a
config bug that does not exist.

Two caveats before you wrap:

  1. Paths cross the boundary. \`wsl.exe -e terraform validate\` runs with the
     WSL view of the filesystem. If the repo is at C:\\repos\\x, WSL sees
     /mnt/c/repos/x - and \`/mnt/c\` is dramatically slower. Prefer moving the
     clone inside WSL and running Claude Code there, which removes this whole
     problem instead of papering over it.
  2. Credentials do not cross. An \`aws\` configured on Windows is not the
     \`aws\` inside WSL; they read different ~/.aws directories.
TXT
fi

if [ -n "$MISSING" ]; then
  cat <<TXT

MISSING TOOLS:$MISSING

A rule naming a tool that is not installed does not fail loudly at setup; it
fails at the gate, on the turn someone needed it, wearing the disguise of a
broken check. Install them, or delete the rules that name them and say in
.crew/STATUS.md that you did.
TXT
fi

exit 0
