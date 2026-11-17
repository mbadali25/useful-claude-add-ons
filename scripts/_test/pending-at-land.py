#!/usr/bin/env python3
"""Suite for scripts/pending-at-land.py and the workflow steps that use it.

Three parts:
  1. must-relax and must-stay-red cases, each running the real wrapper around a
     throwaway child command, with a pull_request event file in a temp
     directory (nothing reads this repository's files or any real event);
  2. the workflow shape: every step that goes through the wrapper is
     draft-only, has a plain twin (`draft != true`) running the same command,
     and its --when text is text the wrapped tool really prints;
  3. mutations: a wrapper that relaxes every failure, one that treats every
     run as a draft, and one that ignores --never must each turn a case red.

Run: python3 scripts/_test/pending-at-land.py
Exit 77 when pyyaml is missing (the workflow part cannot run): NOT RUN.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shlex
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TARGET = os.path.join(os.path.dirname(HERE), "pending-at-land.py")
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "marketplace.yml")
DRAFT_IF = "github.event.pull_request.draft == true"
READY_IF = "github.event.pull_request.draft != true"
# The text each wrapped tool prints for a stale file, and the file that prints it.
PRODUCERS = {
    "python3 docs/guides/crew/src/build.py --check":
        ("docs/guides/crew/src/build.py", 'print(f"stale: ', "stale: crew-guide.html - rebuild"),
    "python3 docs/guides/crew/src/config_reference.py --check":
        ("docs/guides/crew/src/config_reference.py", 'print(f"stale: ', "stale: a.html - regenerate"),
    "python3 plugin/crew/hooks/scripts/crew_standards.py export --check --root .":
        ("plugin/crew/hooks/scripts/crew_standards.py", "standards export STALE: ",
         "standards export STALE: REVIEW.md"),
    "python3 scripts/sync-updates.py --check":
        ("scripts/sync-updates.py", "is stale -- run scripts/sync-updates.py",
         "sync-updates: README.md is stale -- run scripts/sync-updates.py"),
    "python3 scripts/check-changelog.py":
        ("scripts/check-changelog.py", 'f"MISSING: ',
         "check-changelog: MISSING: crew 1.3.1 (set in abc1234) has no CHANGELOG.md entry."),
}


def load():
    spec = importlib.util.spec_from_file_location("pending_at_land", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child(code, *lines):
    """argv for a throwaway command that prints `lines` and exits `code`."""
    body = "import sys\n" + "".join(f"print({line!r})\n" for line in lines) + f"sys.exit({code})\n"
    return [sys.executable, "-c", body]


def event(tmp, payload):
    path = os.path.join(tmp, "event.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    return {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": path}


DRAFT = {"pull_request": {"draft": True}}
READY = {"pull_request": {"draft": False}}
STALE = ("--when", "^stale:")


def cases():
    """(label, expected exit, env builder(tmp) -> environ, wrapper argv)."""
    def draft(tmp):
        return event(tmp, DRAFT)

    def ready(tmp):
        return event(tmp, READY)

    return (
        ("RELAX a draft, exit 1, the stale text", 0, draft, [*STALE, "--", *child(1, "stale: a.html")]),
        ("RELAX with --never given and not matched", 0, draft,
         [*STALE, "--never", "REFUSED", "--", *child(1, "stale: a.html")]),
        ("PASS a passing command on a draft", 0, draft, [*STALE, "--", *child(0, "ok")]),
        ("PASS a passing command on a ready PR", 0, ready, [*STALE, "--", *child(0, "ok")]),
        ("RED a ready PR's stale check is not relaxed", 1, ready,
         [*STALE, "--", *child(1, "stale: a.html")]),
        ("RED a push run (no pull_request event) is not relaxed", 1,
         lambda tmp: {"GITHUB_EVENT_NAME": "push"}, [*STALE, "--", *child(1, "stale: a.html")]),
        ("RED a local run (no GitHub environment) is not relaxed", 1, lambda tmp: {},
         [*STALE, "--", *child(1, "stale: a.html")]),
        ("RED an unreadable event file is not a draft", 1, lambda tmp: event(tmp, "{not json"),
         [*STALE, "--", *child(1, "stale: a.html")]),
        ("RED a missing event file is not a draft", 1,
         lambda tmp: {"GITHUB_EVENT_NAME": "pull_request",
                      "GITHUB_EVENT_PATH": os.path.join(tmp, "absent.json")},
         [*STALE, "--", *child(1, "stale: a.html")]),
        ("RED draft: \"true\" as a string is not a draft", 1,
         lambda tmp: event(tmp, {"pull_request": {"draft": "true"}}),
         [*STALE, "--", *child(1, "stale: a.html")]),
        ("RED exit 2 (the check did not run) stays 2 on a draft", 2, draft,
         [*STALE, "--", *child(2, "stale: a.html")]),
        ("RED exit 77 (could not tell) stays 77 on a draft", 77, draft,
         [*STALE, "--", *child(77, "stale: a.html")]),
        ("RED exit 1 without the stale text is a real failure", 1, draft,
         [*STALE, "--", *child(1, "Traceback (most recent call last):")]),
        ("RED exit 1 with the stale text AND the --never text", 1, draft,
         ["--when", "STALE:", "--never", "REFUSED", "--",
          *child(1, "standards export STALE: x", "standards export REFUSED: y")]),
        ("USAGE no --when", 2, draft, ["--", *child(1, "stale: a")]),
        ("USAGE no command", 2, draft, [*STALE, "--"]),
        ("USAGE no separator", 2, draft, [*STALE, *child(1, "stale: a")]),
        ("USAGE an unknown flag", 2, draft, [*STALE, "--force", "x", "--", *child(1, "stale: a")]),
        ("USAGE a command that cannot start", 2, draft,
         [*STALE, "--", os.path.join("no", "such", "program")]),
    )


def run_all(module):
    failures = []
    for label, want, build_env, argv in cases():
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                got = module.main(list(argv), build_env(tmp))
        ok = got == want
        if ok and label.startswith("RELAX"):
            ok = "pending at land" in out.getvalue()
        print(("ok   " if ok else "FAIL ") + label + ("" if ok else f"  (exit {got}, wanted {want})"))
        if not ok:
            failures.append(label)
    return failures


def workflow_problems(doc, module):
    """Problems with how a workflow document uses the wrapper; [] when sound."""
    out, relaxed = [], 0
    for job_id, job in ((doc or {}).get("jobs") or {}).items():
        steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
        for step in steps:
            run = str(step.get("run", ""))
            if "scripts/pending-at-land.py" not in run:  # not this suite's own step
                continue
            relaxed += 1
            where = f"job {job_id}: step {step.get('name')!r}"
            if " ".join(str(step.get("if", "")).split()) != DRAFT_IF:
                out.append(f"{where}: is not limited to draft PRs (`if: {DRAFT_IF}`)")
            words = shlex.split(run)
            parsed = module.parse(words[2:]) if words[:2] == ["python3", "scripts/pending-at-land.py"] \
                else None
            if parsed is None:
                out.append(f"{where}: could not read the wrapper's arguments")
                continue
            when, never, command = parsed
            plain = " ".join(command)
            twins = [s for s in steps if " ".join(str(s.get("run", "")).split()) == plain]
            if not any(" ".join(str(s.get("if", "")).split()) == READY_IF for s in twins):
                out.append(f"{where}: no plain twin step runs `{plain}` with `if: {READY_IF}`")
            producer = PRODUCERS.get(plain)
            if producer is None:
                out.append(f"{where}: `{plain}` is not a check this suite knows the stale text of")
                continue
            rel, literal, sample = producer
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                if literal not in fh.read():
                    out.append(f"{where}: {rel} no longer prints {literal!r}")
            if not module.pending(1, sample, when, never, True):
                out.append(f"{where}: --when {when.pattern!r} does not match {sample!r}")
            if module.pending(1, "Traceback (most recent call last):", when, never, True):
                out.append(f"{where}: --when {when.pattern!r} relaxes an unrelated failure")
    return relaxed, out


def fixture(step_if=DRAFT_IF, twin_if=READY_IF, when="'^stale:'"):
    plain = "python3 docs/guides/crew/src/build.py --check"
    steps = [{"name": "plain", "run": plain}, {
        "name": "draft", "run": f"python3 scripts/pending-at-land.py --when {when} -- {plain}"}]
    if twin_if:
        steps[0]["if"] = twin_if
    if step_if:
        steps[1]["if"] = step_if
    return {"jobs": {"check": {"steps": steps}}}


SHAPES = (
    ("SHAPE the committed shape passes", fixture(), None),
    ("SHAPE a relaxed step with no `if` fails", fixture(step_if=None), "not limited to draft"),
    ("SHAPE a relaxed step on ready PRs fails", fixture(step_if=READY_IF), "not limited to draft"),
    ("SHAPE a plain twin that is not ready-only fails", fixture(twin_if=None), "no plain twin"),
    ("SHAPE a --when that matches nothing the tool prints fails", fixture(when="'^outdated:'"),
     "does not match"),
    ("SHAPE a --when that matches everything fails", fixture(when="'.'"), "relaxes an unrelated"),
)


def run_shapes(module, yaml):
    failures = []
    for label, doc, text in SHAPES:
        _, got = workflow_problems(doc, module)
        ok = (not got) if text is None else any(text in p for p in got)
        print(("ok   " if ok else "FAIL ") + label + ("" if ok else f"  -> {got}"))
        if not ok:
            failures.append(label)
    with open(WORKFLOW, encoding="utf-8") as fh:
        relaxed, got = workflow_problems(yaml.safe_load(fh), module)
    ok = not got and relaxed == len(PRODUCERS)
    print(("ok   " if ok else "FAIL ") + f"SHAPE marketplace.yml: {relaxed} relaxed step(s), "
          f"{len(PRODUCERS)} expected" + ("" if ok else f"  -> {got}"))
    if not ok:
        failures.append("marketplace.yml")
    return failures


def main():
    try:
        import yaml  # pylint: disable=import-outside-toplevel
    except ImportError:
        print("pending-at-land suite: pyyaml not importable; NOT RUN")
        return 77
    module = load()
    failures = run_all(module) + run_shapes(module, yaml)
    if failures:
        print(f"{len(failures)} case(s) failed")
        return 1
    # Sabotage: each mutated wrapper must turn at least one case red.
    original_pending, original_draft = module.pending, module.is_draft
    mutations = (
        ("relax-every-failure", "pending", lambda code, *_a: code != 0),
        ("every-run-is-a-draft", "is_draft", lambda _env: True),
        ("ignore --never", "pending",
         lambda code, output, when, never, draft: original_pending(code, output, when, None, draft)),
        ("ignore the exit code", "pending",
         lambda code, output, when, never, draft: original_pending(1, output, when, never, draft)),
    )
    for label, name, replacement in mutations:
        setattr(module, name, replacement)
        with contextlib.redirect_stdout(io.StringIO()):
            red = run_all(module)
        module.pending, module.is_draft = original_pending, original_draft
        if not red:
            print(f"SABOTAGE NOT DETECTED: the {label} mutation left the suite green")
            return 1
        print(f"ok   sabotage {label}: {len(red)} case(s) went red")
    total = len(cases()) + len(SHAPES) + 1
    print(f"pending-at-land: all {total} cases passed, {len(mutations)} mutations detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
