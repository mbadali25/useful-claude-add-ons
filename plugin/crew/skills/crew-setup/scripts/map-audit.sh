#!/usr/bin/env bash
# Reconciles .crew/verify.json against the checks that actually exist on disk.
# Reports both directions of drift. Read-only.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 1
[ -f .crew/verify.json ] || { echo "no .crew/verify.json - run /crew:verify"; exit 0; }

# Resolve the python FAMILY, the same way resolve-tools.sh:20 does over the
# same map. A bare `python3` is not portable to Git Bash, which ships without
# it: on a machine that has `python` but not `python3` this audit died at 127
# for no reason, and 127 from a shell is not a sentence anyone can act on.
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || command -v py 2>/dev/null) || PY=""
if [ -z "$PY" ]; then
  echo "map-audit: no python found (tried python3, python, py) - cannot audit .crew/verify.json. Install one, or run the audit from a shell that has it." >&2
  exit 1
fi

"$PY" - << 'PY'
import json, os, glob, re, sys

vm = json.load(open(".crew/verify.json"))

# A command is ONE LINE. The same rule verify-gate.sh and resolve-tools.sh
# enforce over the same map, refused in the same words: three readers of `run`
# that disagree about what a rule IS would let setup write a map the gate then
# refuses at the end of a turn. Here the symptom was a false report rather than
# a skipped check - the `.sh|.py|...` token scan below runs over the joined
# text, so half of a multi-line entry reads as a filename and is reported under
# "rules pointing at files that do not exist", sending the reader after a file
# nobody named. A report drawn from a map crew cannot represent is not a
# report, so this refuses to print one.
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

for ri, rule in enumerate(vm.get("rules", []) or []):
    if isinstance(rule, dict):
        reject_unrepresentable(f"rules[{ri}].run", rule.get("run"))
reject_unrepresentable("always", vm.get("always"))
reject_unrepresentable("default", vm.get("default"))

cmds = []
for r in vm.get("rules", []): cmds += r.get("run", [])
cmds += vm.get("always", []) + vm.get("default", [])
blob = " ".join(cmds)

# Checks that exist on disk
found = []
for pat in ("scripts/smoke.sh", "_verify/**/*", "qa/**/*",
            "e2e/**/*.spec.*", "e2e/**/*.test.*",
            "tests/**/*", "test/**/*", "spec/**/*",
            "**/*_test.py", "**/*Tests.cs", "**/*Test.php"):
    for f in glob.glob(pat, recursive=True):
        if os.path.isfile(f) and "node_modules" not in f and ".git" not in f:
            found.append(f)

def referenced(path):
    if path in blob: return True
    base = os.path.basename(path)
    if base in blob: return True
    # a rule may invoke the whole directory or a runner that globs it
    d = os.path.dirname(path)
    while d and d != ".":
        if d in blob: return True
        d = os.path.dirname(d)
    return False

orphans = sorted({f for f in found if not referenced(f)})

# Rules pointing at scripts that no longer exist
missing = []
for c in cmds:
    for tok in re.findall(r'[\w./\-]+\.(?:sh|py|ps1|js|ts)\b', c):
        p = tok.lstrip("./")
        if not os.path.exists(p) and not os.path.exists(tok):
            missing.append((c, tok))

print("== checks on disk with no rule (they never run) ==")
if orphans:
    for f in orphans[:40]: print("  ", f)
    if len(orphans) > 40: print(f"   ... and {len(orphans)-40} more")
else:
    print("   none")

print()
print("== rules pointing at files that do not exist ==")
if missing:
    for c, t in missing: print(f"   {t}   (in: {c})")
else:
    print("   none")

print()
print(f"rules: {len(vm.get('rules', []))}   checks found: {len(found)}   orphaned: {len(orphans)}")
print()
print("An orphaned check is the dangerous one: it looks like coverage and never runs.")
print("Check before acting: a runner that globs a directory (pytest, playwright)")
print("may cover files this cannot see - but a restrictive --grep or -k means it")
print("does not, which is exactly the gap worth finding.")
PY
STATUS=$?
# Exit 4 is the ONLY status meaning "the map names a command crew cannot
# represent"; the PARSE_ERROR above says which entry. Translated to 2 so this
# script agrees with verify-gate.sh and resolve-tools.sh on the exit code as
# well as on the message. Still read-only: nothing was written either way.
if [ "$STATUS" -eq 4 ]; then
  echo "map-audit: refusing to audit .crew/verify.json - it names a command crew cannot represent (see the PARSE_ERROR above). Fix that entry first; verify-gate.sh refuses the same map." >&2
  exit 2
fi
exit "$STATUS"
