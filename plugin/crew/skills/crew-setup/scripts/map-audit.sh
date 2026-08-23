#!/usr/bin/env bash
# Reconciles .crew/verify.json against the checks that actually exist on disk.
# Reports both directions of drift. Read-only.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 1
[ -f .crew/verify.json ] || { echo "no .crew/verify.json - run /crew:verify"; exit 0; }

python3 - << 'PY'
import json, os, glob, re, sys

vm = json.load(open(".crew/verify.json"))
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
