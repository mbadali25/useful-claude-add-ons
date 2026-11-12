#!/usr/bin/env python3
"""Suite: a draft PR's --pending-bump run can never satisfy a required check.

marketplace.yml's `check` job runs check-marketplace.py with --pending-bump on
a DRAFT pull request, which passes version drift as "pending at land". Branch
protection requires the `check` context (strict, admins not exempt). If the
draft run reports under that same name, a PR marked ready can merge on the
draft run's green before the full ready_for_review run reports: PR #758 did,
6 s after it was marked ready, and main went red.

The rule this suite holds, for every job in every workflow that has a
--pending-bump step:
  - on a draft PR its check-run name must not be a REQUIRED context;
  - on a ready PR, push or manual run it must still report `check`, or every
    PR would wait forever for a context nothing reports;
  - it must carry no job-level `if:`, because a skipped job reports a
    conclusion branch protection accepts;
  - neither the job nor any of its steps may carry `continue-on-error`
    (other than a literal false), because a failing step under it leaves the
    job, and so the required context, green.
A job name this suite cannot evaluate is a failure ("could not tell"), never
a pass.

REQUIRED mirrors main's branch protection as read with
`gh api repos/mbadali25/useful-claude-add-ons/branches/main/protection/required_status_checks`
on 2026-11-11. Change both together.

Run: python3 scripts/_test/draft-check-name.py
"""

from __future__ import annotations

import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - the CI job installs pyyaml first
    print("draft-check-name: pyyaml not importable; NOT RUN")
    sys.exit(77)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WFDIR = os.path.join(ROOT, ".github", "workflows")

REQUIRED = (
    "check", "shell", "build (3.11)", "build (3.12)", "build (3.13)",
    "test (3.11)", "test (3.12)", "test (3.13)", "test (ubuntu-latest)",
    "test (windows-latest)", "crew-shell-matrix (windows-latest)",
)
FULL_NAME = "check"
DRAFT = "github.event.pull_request.draft"
# The one expression form evaluated: `${{ <DRAFT> && 'a' || 'b' }}`.
TERNARY = re.compile(r"^\$\{\{\s*" + re.escape(DRAFT)
                     + r"\s*&&\s*'([^']*)'\s*\|\|\s*'([^']*)'\s*\}\}$")


def job_name(job_id: str, job: dict, draft: bool):
    """The check-run name for this job, or None when it cannot be told."""
    name = job.get("name", job_id)
    if not isinstance(name, str):
        return None
    if "${{" not in name:
        return name
    m = TERNARY.match(name.strip())
    if not m:
        return None
    return m.group(1) if draft else m.group(2)


def is_required(name: str, has_matrix: bool) -> bool:
    if name in REQUIRED:
        return True
    return has_matrix and any(r.startswith(name + " (") for r in REQUIRED)


def has_pending_bump(job: dict) -> bool:
    return any("--pending-bump" in str(step.get("run", ""))
               for step in job.get("steps") or [] if isinstance(step, dict))


def problems(doc: dict, wf: str) -> list:
    out = []
    jobs = (doc or {}).get("jobs") or {}
    for job_id, job in jobs.items():
        if not isinstance(job, dict) or not has_pending_bump(job):
            continue
        where = f"{wf}: job {job_id}"
        if "if" in job:
            out.append(f"{where}: has a job-level `if:`; a skipped job reports a "
                       "conclusion branch protection accepts")
        if job.get("continue-on-error", False) is not False:
            out.append(f"{where}: has a job-level `continue-on-error`; a failure "
                       "would not fail the required context")
        for n, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict) and step.get("continue-on-error", False) is not False:
                label = step.get("name") or step.get("run") or step.get("uses") or f"#{n + 1}"
                out.append(f"{where}: step {label!r} has `continue-on-error`; its "
                           "failure would leave the required context green")
        draft_name = job_name(job_id, job, draft=True)
        full_name = job_name(job_id, job, draft=False)
        if draft_name is None or full_name is None:
            out.append(f"{where}: could not tell its check-run name from "
                       f"{job.get('name')!r}")
            continue
        matrix = bool((job.get("strategy") or {}).get("matrix"))
        if is_required(draft_name, matrix):
            out.append(f"{where}: a draft run (--pending-bump) reports the REQUIRED "
                       f"context {draft_name!r}")
        if full_name != FULL_NAME:
            out.append(f"{where}: the full run reports {full_name!r}, not the "
                       f"required {FULL_NAME!r}")
    return out


def repo_problems() -> tuple:
    found, out = 0, []
    for wf in sorted(os.listdir(WFDIR)):
        if not wf.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(WFDIR, wf), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        found += sum(1 for j in ((doc or {}).get("jobs") or {}).values()
                     if isinstance(j, dict) and has_pending_bump(j))
        out += problems(doc, wf)
    return found, out


def fixture(name=None, job_if=None, matrix=False, job_coe=None, step_coe=None) -> dict:
    job = {"runs-on": "ubuntu-latest", "steps": [
        {"run": "python3 scripts/check-marketplace.py", "if": f"{DRAFT} != true"},
        {"run": "python3 scripts/check-marketplace.py --pending-bump", "if": f"{DRAFT} == true"},
    ]}
    if name is not None:
        job["name"] = name
    if job_if is not None:
        job["if"] = job_if
    if matrix:
        job["strategy"] = {"matrix": {"python-version": ["3.11"]}}
    if job_coe is not None:
        job["continue-on-error"] = job_coe
    if step_coe is not None:
        job["steps"].append({"name": "a suite", "run": "python3 x.py",
                             "continue-on-error": step_coe})
    return {"jobs": {"check": job}}


FIXED = "${{ " + DRAFT + " && 'check-draft (version bump pending at land)' || 'check' }}"
CASES = (
    # (label, doc, must_fail, text the failure must contain)
    ("the fixed shape passes", fixture(FIXED), False, ""),
    ("no spaces in the expression still evaluates", fixture(FIXED.replace(" && ", "&&")
                                                            .replace(" || ", "||")), False, ""),
    ("the pre-fix shape (no name: draft reports `check`) fails", fixture(), True,
     "draft run (--pending-bump) reports the REQUIRED context 'check'"),
    ("a literal name `check` fails", fixture("check"), True, "REQUIRED context 'check'"),
    ("an inverted expression fails", fixture("${{ " + DRAFT + " && 'check' || 'check-draft' }}"),
     True, "REQUIRED context 'check'"),
    ("a draft name equal to another required context fails",
     fixture("${{ " + DRAFT + " && 'shell' || 'check' }}"), True, "REQUIRED context 'shell'"),
    ("a matrix leg of `build` fails", fixture("${{ " + DRAFT + " && 'build' || 'check' }}",
                                              matrix=True), True, "REQUIRED context 'build'"),
    ("a full run not named `check` fails (every PR would wait forever)",
     fixture("${{ " + DRAFT + " && 'check-draft' || 'check-full' }}"), True,
     "the full run reports 'check-full'"),
    ("an expression it cannot evaluate fails as could-not-tell",
     fixture("${{ format('check{0}', " + DRAFT + ") }}"), True, "could not tell"),
    ("a job-level if (skipped job) fails", fixture(FIXED, job_if=f"{DRAFT} != true"), True,
     "job-level `if:`"),
    ("a step with continue-on-error: true fails", fixture(FIXED, step_coe=True), True,
     "step 'a suite' has `continue-on-error`"),
    ("a step with a continue-on-error expression fails",
     fixture(FIXED, step_coe="${{ " + DRAFT + " }}"), True, "has `continue-on-error`"),
    ("a step with continue-on-error: false passes", fixture(FIXED, step_coe=False), False, ""),
    ("a job-level continue-on-error fails", fixture(FIXED, job_coe=True), True,
     "job-level `continue-on-error`"),
    ("a job with no --pending-bump step is not judged",
     {"jobs": {"check": {"steps": [{"run": "python3 scripts/check-marketplace.py"}]}}}, False, ""),
)


def main() -> int:
    failed = 0
    for label, doc, must_fail, text in CASES:
        got = problems(doc, "fixture.yml")
        ok = (bool(got) and any(text in p for p in got)) if must_fail else not got
        print(f"{'PASS' if ok else 'FAIL'}: {label}" + ("" if ok else f" -> {got}"))
        failed += not ok
    found, got = repo_problems()
    if found == 0:
        print("FAIL: this repo: no job with a --pending-bump step found; "
              "the suite would be checking nothing")
        failed += 1
    elif got:
        print("FAIL: this repo's workflows:\n  " + "\n  ".join(got))
        failed += 1
    else:
        print(f"PASS: this repo's workflows ({found} --pending-bump job(s), none can "
              "satisfy a required context from a draft run)")
    total = len(CASES) + 1
    print(f"draft-check-name: {total - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
