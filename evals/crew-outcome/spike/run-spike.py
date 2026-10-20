#!/usr/bin/env python3
"""The L-0728 spike, reproducible: one throwaway S task run once per arm, through
the harness itself (billed: a few US dollars in all).

    python3 evals/crew-outcome/spike/run-spike.py --work DIR --canary canary.txt

It builds a source repository from `base/` (commit 1) and `reference/` (commit 2),
a task directory (statement, frozen hidden tests, defects), then runs
`validate`, `run --arm baseline`, `run --arm crew` and `report` from
scripts/crew-outcome-eval.py. Needs the image (container/Dockerfile) and a
passing canary output. Nothing here is a scored result.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
HARNESS = os.path.join(REPO, "scripts", "crew-outcome-eval.py")
GIT = ("git", "-c", "user.name=spike", "-c", "user.email=spike@invalid")

DEFECTS = {
    "separators": ["tests/test_slug.py::test_slugify_basic", "tests/test_slug.py::test_slugify_collapses_runs",
                   "tests/test_slug.py::test_slugify_strips_hyphens"],
    "empty": ["tests/test_slug.py::test_slugify_empty"],
    "non-ascii": ["tests/test_slug.py::test_slugify_non_ascii_is_a_separator"],
    "types": [f"tests/test_slug.py::test_slugify_rejects_non_str[{v}]" for v in ("None", "3", "x", "value3")],
}


def run(*argv, cwd=None):
    out = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit(f"{' '.join(argv[:4])} failed ({out.returncode}): {out.stderr.strip()}")
    return out.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--canary", required=True, help="a passing canary.sh output")
    parser.add_argument("--arms", default="baseline,crew")
    args = parser.parse_args()
    work = os.path.abspath(args.work)
    src = os.path.join(work, "src")
    tasks = os.path.join(work, "tasks")
    results_dir = os.path.join(work, "results")
    shutil.rmtree(work, ignore_errors=True)
    for path in (src, results_dir):
        os.makedirs(path)
    run("git", "init", "-q", "-b", "main", cwd=src)
    shutil.copytree(os.path.join(HERE, "base"), src, dirs_exist_ok=True)
    run("git", "add", "-A", cwd=src)
    run(*GIT, "commit", "-q", "-m", "base", cwd=src)
    base = run("git", "rev-parse", "HEAD", cwd=src)
    shutil.copyfile(os.path.join(HERE, "reference", "slug.py"), os.path.join(src, "slug.py"))
    shutil.copyfile(os.path.join(HERE, "grading", "tests", "test_slug.py.frozen"),
                    os.path.join(src, "tests", "test_slug.py"))
    run("git", "add", "-A", cwd=src)
    run(*GIT, "commit", "-q", "-m", "reference", cwd=src)
    reference = run("git", "rev-parse", "HEAD", cwd=src)
    task = os.path.join(tasks, "spike-slug")
    os.makedirs(os.path.join(task, "grading", "tests"))
    shutil.copyfile(os.path.join(HERE, "statement.md"), os.path.join(task, "statement.md"))
    shutil.copyfile(os.path.join(HERE, "grading", "tests", "test_slug.py.frozen"),
                    os.path.join(task, "grading", "tests", "test_slug.py.frozen"))
    with open(os.path.join(task, "task.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": "spike-slug", "ticket": "L-0000", "repo": "spike", "base": base, "reference": reference,
                   "bucket": "S", "referenceLines": 6, "statementFile": "statement.md", "defects": DEFECTS,
                   "regressionInventory": ["tests/test_slug.py::test_titlecase"],
                   "gradingFiles": ["tests/test_slug.py"],
                   "testCommand": ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rA",
                                   "tests/test_slug.py"]}, fh)
    shutil.copyfile(args.canary, os.path.join(results_dir, "canary.txt"))
    common = [sys.executable, HARNESS, "--tasks-dir", tasks, "--source-repo", src]
    results = os.path.join(results_dir, "results.jsonl")
    print(run(*common, "validate", "--all"))
    for arm in args.arms.split(","):
        print(run(*common, "run", "--all", "--arm", arm, "--runs", "1", "--results", results,
                  "--runs-dir", os.path.join(work, "runs"), "--max-cost-usd", "30"))
    print(run(*common, "report", "--results", results))


if __name__ == "__main__":
    main()
