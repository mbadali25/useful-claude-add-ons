"""Sabotage test: reintroduce each bug and confirm the suite goes red.

Run it directly: `python3 plugin/crew/tests/sabotage.py`. It patches a file,
runs the test that should catch the change, and restores the file whether or
not the run succeeded.

A test that stays green with the behaviour deleted proves nothing. Codex
found three of those in this PR; these are the exact mutations it named.
"""
import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))) + "/"
CREW = ROOT + "plugin/crew/"
STATE = CREW + "hooks/scripts/crew_state.py"
LADDER_DOC = CREW + "skills/crew-scaling/SKILL.md"


def run(tests):
    r = subprocess.run(
        [sys.executable, "-m", "pytest"] + tests + ["-q", "--no-header", "-x"],
        cwd=CREW, capture_output=True, text=True)
    return r.returncode


MUTATIONS = [
    # (label, path, find, replace, tests that MUST go red)
    (
        "family guard deleted (finding 8)",
        STATE,
        '    if out["family"] is not None and out["family"] in authors:',
        '    if False:',
        ["tests/test_provider_table.py::test_an_unknown_author_family_bars_nothing"],
    ),
    (
        "author_families ignores role pins again (regression)",
        STATE,
        '    decided = resolve_role(cfg, "dev", "developer")',
        '    decided = {"family": family((dict_or_empty(dict_or_empty(cfg).get("dev")).get("provider") or "claude"), None)}',
        ["tests/test_provider_table.py::"
         "test_author_family_honours_a_per_role_dev_pin_over_the_block_default"],
    ),
]


def mutate(path, find, replace):
    s = io.open(path, encoding="utf-8").read()
    if s.count(find) != 1:
        return None
    shutil.copy(path, path + ".bak")
    io.open(path, "w", encoding="utf-8", newline="\n").write(s.replace(find, replace))
    return True


def restore(path):
    shutil.move(path + ".bak", path)


ok = True
for label, path, find, replace, tests in MUTATIONS:
    if not mutate(path, find, replace):
        print(f"SKIP  {label}: anchor not found or not unique")
        ok = False
        continue
    try:
        code = run(tests)
    finally:
        restore(path)
    verdict = "RED (good)" if code != 0 else "STILL GREEN -- TEST IS VACUOUS"
    print(f"{verdict:32} {label}")
    if code == 0:
        ok = False

# Finding 9: a bogus role in the docs table must now be caught.
s = io.open(LADDER_DOC, encoding="utf-8").read()
marker = "| 1 | + security"
if s.count(marker) == 1:
    shutil.copy(LADDER_DOC, LADDER_DOC + ".bak")
    io.open(LADDER_DOC, "w", encoding="utf-8", newline="\n").write(
        s.replace(marker, "| 1 | + ghost-reviewer, + security", 1))
    try:
        code = run(["tests/test_role_ladder.py"])
    finally:
        restore(LADDER_DOC)
    verdict = "RED (good)" if code != 0 else "STILL GREEN -- TEST IS VACUOUS"
    print(f"{verdict:32} bogus documented role (finding 9)")
    if code == 0:
        ok = False
else:
    print(f"SKIP  finding 9: marker count {s.count(marker)}")
    ok = False

print("\nSABOTAGE SUITE:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
