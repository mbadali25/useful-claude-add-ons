#!/usr/bin/env python3
"""Suite for the CI step that runs `crew_standards.py export --check`.

L-0718's standards export (REVIEW.md, AGENTS.md's Code Review Rules block,
.cursor/BUGBOT.md, docs/review-rules/) was checked only by the local
verify.json rule `standards-export`, so a PR could carry stale exports with
every CI check green (PR #754, recorded digest 2c5f9149 against a fresh
216c55f6). marketplace.yml now runs the check. This suite proves two things:

1. The step is in marketplace.yml with the exact command and runs on every
   run, so a later edit that drops it or guards it with `if:` goes red here.
   Since bump at land (docs/landing-prs.md) "every run" has one allowed
   shape besides no `if:` at all: the plain step limited to everything but
   draft PRs, beside a draft-only step that runs the same command through
   scripts/pending-at-land.py (red on anything but a STALE export).
2. The command it runs exits 0 on a current export and 1 on a stale one. Each
   case copies this repository's overlay and generated outputs into a
   throwaway root and runs the REAL script against it with --root; nothing in
   this checkout is written. The stale cases are the ways an export goes stale:
   a different recorded digest (#754's shape), a different recorded crew
   version (a bump without a regenerate), a hand edit, a deleted output, and a
   changed overlay standard with no regenerate.

The final case is a mutation: a workflow text with the step removed must fail
check 1, so the presence check cannot pass by matching nothing.

Run: python3 scripts/_test/standards-export-ci.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "plugin", "crew", "hooks", "scripts", "crew_standards.py")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "marketplace.yml")
COMMAND = "python3 plugin/crew/hooks/scripts/crew_standards.py export --check --root ."

OVERLAY = ".crew/standards.md"
OUTPUTS = ("REVIEW.md", ".cursor/BUGBOT.md", "AGENTS.md")
RULES_DIR = "docs/review-rules"

FAILURES: list[str] = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" - {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


READY_ONLY = "if: github.event.pull_request.draft != true"
DRAFT_ONLY = "if: github.event.pull_request.draft == true"
TWIN_PREFIX = "run: python3 scripts/pending-at-land.py "
NOT_IN_STEP = object()


def step_if(lines, i):
    """The `if:` line (stripped) of the step holding line i, None when the step
    has none, NOT_IN_STEP when line i is not inside a step."""
    indent = len(lines[i]) - len(lines[i].lstrip())
    # Walk back to the step's `- ` line; any `if:` between it and run: guards the step.
    for j in range(i - 1, -1, -1):
        prev = lines[j]
        stripped = prev.strip()
        prev_indent = len(prev) - len(prev.lstrip())
        if stripped.startswith("if:") and prev_indent == indent:
            return " ".join(stripped.split())
        if stripped.startswith("- ") and prev_indent < indent:
            if stripped[2:].startswith("if:"):
                return " ".join(stripped[2:].split())
            return None
    return NOT_IN_STEP


def step_problem(text):
    """None when `text` (a workflow) runs COMMAND on every run, else why not.

    Every run means: a step with no `if:`; or (bump at land) a step limited to
    everything but draft PRs (READY_ONLY) beside a draft-only step that runs the
    same command through scripts/pending-at-land.py, which fails on anything
    but a STALE export. Any other condition, or a ready-only step with no such
    twin, is a check some run skips.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != f"run: {COMMAND}":
            continue
        cond = step_if(lines, i)
        if cond is NOT_IN_STEP:
            return "the run: line is not inside a step"
        if cond is None:
            return None
        if cond != READY_ONLY:
            return f"the step is conditional ({cond})"
        twins = [k for k, other in enumerate(lines)
                 if other.strip().startswith(TWIN_PREFIX) and other.strip().endswith(f" -- {COMMAND}")]
        if any(step_if(lines, k) == DRAFT_ONLY for k in twins):
            return None
        return ("the step skips draft PRs and no draft-only scripts/pending-at-land.py step "
                "runs the same check")
    return f"no step runs `{COMMAND}`"


def fixture(dest):
    """Copy the overlay and every generated output into `dest`."""
    rels = [OVERLAY, *OUTPUTS]
    rules = os.path.join(ROOT, RULES_DIR)
    rels += [f"{RULES_DIR}/{name}" for name in sorted(os.listdir(rules))]
    for rel in rels:
        src = os.path.join(ROOT, *rel.split("/"))
        dst = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
    return rels


def run_check(root):
    done = subprocess.run([sys.executable, SCRIPT, "export", "--check", "--root", root],
                          capture_output=True, text=True, check=False)
    return done.returncode, done.stdout + done.stderr


def first_rules_file(root):
    name = sorted(os.listdir(os.path.join(root, RULES_DIR)))[0]
    return os.path.join(root, RULES_DIR, name)


def sub_marker(path, key, value):
    text = read(path)
    new = re.sub(rf"\b{key}=[0-9A-Za-z.+-]+", f"{key}={value}", text, count=1)
    assert new != text, f"no {key}= in {path}"
    write(path, new)


def hand_edit(root):
    path = os.path.join(root, "REVIEW.md")
    write(path, read(path) + "\nA line nobody generated.\n")


def delete_output(root):
    os.remove(os.path.join(root, ".cursor", "BUGBOT.md"))


def change_overlay(root):
    path = os.path.join(root, *OVERLAY.split("/"))
    text = read(path)
    new = re.sub(r"(\*\*Rule\*\*[^\n]*?)(\n)", r"\1 Changed and not regenerated.\2", text, count=1)
    if new == text:  # the overlay's field markup changed; any byte change in a standard will do
        new = text.replace("REPO-01", "REPO-01 (edited)", 1)
    assert new != text, "could not change the overlay"
    write(path, new)


STALE = (
    ("recorded digest differs (PR #754's shape)",
     lambda root: sub_marker(first_rules_file(root), "digest", "2c5f9149" + "0" * 56)),
    ("recorded crew version differs (bump without regenerate)",
     lambda root: sub_marker(os.path.join(root, "REVIEW.md"), "crew", "0.0.0")),
    ("hand edit to REVIEW.md", hand_edit),
    ("generated .cursor/BUGBOT.md deleted", delete_output),
    ("overlay standard changed, exports not regenerated", change_overlay),
)


def main():
    workflow = read(WORKFLOW)
    problem = step_problem(workflow)
    check("marketplace.yml runs the export check on every run", problem is None, problem or "")

    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "current")
        fixture(base)
        code, out = run_check(base)
        check("current export: check exits 0", code == 0, f"exit {code}: {out.strip()}")
        check("current export: says current", "standards export current" in out, out.strip())

        for i, (name, mutate) in enumerate(STALE):
            root = os.path.join(tmp, f"stale{i}")
            shutil.copytree(base, root)
            mutate(root)
            code, out = run_check(root)
            check(f"stale: {name}: check exits 1", code == 1, f"exit {code}: {out.strip()}")
            check(f"stale: {name}: says STALE", "standards export STALE" in out, out.strip())

    # Mutation: the presence check must fail on a workflow without the step,
    # and on one that guards it with `if:`.
    removed = "\n".join(line for line in workflow.splitlines()
                        if line.strip() != f"run: {COMMAND}")
    check("mutation: step removed is caught", step_problem(removed) is not None)
    lines = workflow.splitlines()  # line-wise: a CRLF checkout must not hide the mutation
    at = next((i for i, line in enumerate(lines) if line.strip() == f"run: {COMMAND}"), 0)
    guarded = lines[:at - 1] + ["        if: false"] + lines[at:]
    check("mutation: step guarded with if: is caught",
          at > 0 and lines[at - 1].strip() == READY_ONLY
          and step_problem("\n".join(guarded)) is not None)
    # Bump at land: the ready-only condition is allowed only beside its draft twin.
    plain = f"      - name: x\n        run: {COMMAND}\n"
    ready = f"      - name: x\n        {READY_ONLY}\n        run: {COMMAND}\n"
    twin = (f"      - name: y\n        {DRAFT_ONLY}\n        {TWIN_PREFIX}--when 'standards export "
            f"STALE:' --never 'REFUSED' -- {COMMAND}\n")
    check("shape: an unconditional step passes", step_problem(plain) is None)
    check("shape: ready-only beside a draft-only pending-at-land twin passes",
          step_problem(ready + twin) is None)
    check("mutation: ready-only with no draft twin is caught", step_problem(ready) is not None)
    check("mutation: a twin that is not draft-only is caught",
          step_problem(ready + twin.replace(f"        {DRAFT_ONLY}\n", "")) is not None)
    check("mutation: a twin that runs another command is caught",
          step_problem(ready + twin.replace(COMMAND, COMMAND + " --dry-run")) is not None)
    check("mutation: a draft-only plain step is caught",
          step_problem(ready.replace(READY_ONLY, DRAFT_ONLY) + twin) is not None)

    print(f"\n{len(FAILURES)} failure(s)" if FAILURES else "\nall cases passed")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
