#!/usr/bin/env python3
"""Suite for scripts/ci-select.py, which decides the heavy Linux CI suites a
pull request runs in pytest-crew.yml, pylint.yml, shell-suites.yml and
mcp-servers.yml (C-0001).

A wrong answer there is a suite skipped on a PR that needed it, and nothing
goes red: the skip reads as a pass until main's push run. So the cases that
matter most are the must-run ones -- every way a change could be read as
"documentation only" or "only that component" when it is not -- and the
fail-closed ones: no diff, a diff error, an exception, all select everything.

Every case runs the script as a subprocess, in a throwaway git repository when
it needs a real diff. Nothing here reads or writes this checkout except the
workflows and scripts/gate-runner.py, which it parses to check the wiring.

Run: python3 scripts/_test/ci-select.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "scripts", "ci-select.py")
WORKFLOWS = ("pytest-crew.yml", "pylint.yml", "shell-suites.yml", "mcp-servers.yml")
NEVER_SELECTED = ("marketplace.yml", "instruction-budgets.yml", "verify-gate.yml", "plugin-evals.yml")
CREW = "plugin/crew/tests/"
# The two crew files every document selects: one reads every tracked file,
# the other every .md and .html.
DOC_SCAN = {CREW + "test_sendkeys_structural_gate.py", CREW + "test_crew_instructions.py"}
TIMEOUT = 60


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses look their module up here
    spec.loader.exec_module(mod)
    return mod


SEL = load(SCRIPT, "ci_select")
KEYS = SEL.KEYS


def run(args, cwd=None):
    done = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                          cwd=cwd or REPO, timeout=TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout, done.stderr


def parse(stdout):
    out = {}
    for line in stdout.splitlines():
        if "=" in line and not line.startswith(("::", "ci-select")):
            key, value = line.split("=", 1)
            out[key] = value
    return out


def select_paths(paths, event="pull_request"):
    with tempfile.TemporaryDirectory() as tmp:
        listing = os.path.join(tmp, "paths.txt")
        pathlib.Path(listing).write_text("".join(p + "\n" for p in paths), encoding="utf-8")
        rc, out, err = run(["--event", event, "--paths-from", listing])
    if rc != 0:
        raise AssertionError(f"ci-select exited {rc}: {err}")
    return parse(out), out


def selected(got):
    return {k for k in KEYS if got.get(k) == "true"}


def is_all(got):
    return (got.get("all") == "true" and selected(got) == set(KEYS) and got.get("lint") == "true"
            and got.get("combined") == "true"
            and got.get("pytest_combined", "").split() == list(SEL.COMBINED))


FAILURES = []


def expect(cond, msg):
    if not cond:
        FAILURES.append(msg)


# ---- must skip: plain documentation selects nothing but the doc scan --------

def case_docs_only_selects_only_the_doc_scan():
    for paths in (["docs/handoff/x.md"], ["notes-2026.md"], ["docs/handoff/a.md", "docs/review/b.md"],
                  ["docs/adr/0009-new-decision.md"]):
        got, out = select_paths(paths)
        expect(selected(got) == set() and got["lint"] == "false" and got["all"] == "false",
               f"{paths}: a plain document selected {selected(got)}, lint={got.get('lint')}")
        expect(set(got["pytest_combined"].split()) == DOC_SCAN,
               f"{paths}: the doc scans are the only pytest paths, got {got['pytest_combined']!r}")
        expect("SKIPPED, not passed" in out, f"{paths}: no SKIPPED notice:\n{out}")


# ---- must select one component -----------------------------------------------

def case_one_component_selects_only_that_component():
    rows = (
        (["plugin/gizmoduck/scripts/routine.py"], {"gizmoduck"}, ["plugin/gizmoduck/scripts/_test/"]),
        (["skills/notify/scripts/notify.py"], {"notify"}, ["skills/notify/tests/"]),
        (["skills/cisco-meraki/scripts/meraki_http.py"], {"cisco_meraki"}, []),
        (["skills/wazuh-onprem/scripts/manager_config.py"], {"wazuh_onprem"}, []),
        (["mcp-servers/packages/core/src/index.ts"], {"mcp_servers"}, []),
        (["skills/jira-manager/scripts/jira-api.sh"], {"jira_manager"}, []),
    )
    for paths, want, combined in rows:
        got, _ = select_paths(paths)
        expect(selected(got) == want, f"{paths}: selected {selected(got)}, expected {want}")
        dirs = [p for p in got["pytest_combined"].split() if not p.startswith(CREW + "test_")]
        expect(dirs == combined, f"{paths}: pytest_combined dirs {dirs}, expected {combined}")
        expect(got["crew"] == "false", f"{paths}: selected crew's whole suite")


def case_crew_selects_the_whole_crew_suite():
    for path in ("plugin/crew/hooks/scripts/crew_state.py", "plugin/crew/commands/status.md",
                 "plugin/crew/hooks/hooks.json", "plugin/crew/README.md"):
        got, _ = select_paths([path])
        expect("crew" in selected(got), f"{path}: crew not selected: {selected(got)}")
        expect("plugin/crew/tests/" in got["pytest_combined"].split(),
               f"{path}: crew's test directory is not in the combined run")


def case_a_skill_md_selects_its_skill():
    got, _ = select_paths(["skills/notify/SKILL.md"])
    expect("notify" in selected(got), f"skills/notify/SKILL.md did not select notify: {selected(got)}")
    got, _ = select_paths(["plugin/crew/skills/crew-setup/SKILL.md"])
    expect("crew" in selected(got), "a crew SKILL.md did not select crew")


def case_two_components_select_both_and_not_everything():
    got, _ = select_paths(["plugin/gizmoduck/scripts/routine.py", "skills/notify/scripts/notify.py"])
    expect({"gizmoduck", "notify"} <= selected(got) and got["all"] == "false",
           f"two components: selected {selected(got)}, all={got['all']}")


def case_python_in_a_component_selects_lint_and_markdown_does_not():
    got, _ = select_paths(["skills/notify/scripts/notify.py"])
    expect(got["lint"] == "true", "a .py change did not select lint")
    got, _ = select_paths(["skills/notify/SKILL.md"])
    expect(got["lint"] == "false", "a SKILL.md change selected lint")


# ---- the combined pytest run is one session ----------------------------------

COMBINED_KEYS = {key for key, _root, d in SEL.COMPONENTS if d}


def case_a_change_that_can_alter_the_combined_session_selects_all_of_it():
    # Test modules have no __init__.py, so a basename in two combined dirs
    # collides only when both are collected; a conftest or pytest config in
    # one dir changes the whole session. A subset run cannot see either.
    for path in ("skills/notify/tests/test_status_vocabulary.py", "skills/notify/tests/helpers.py",
                 "plugin/gizmoduck/scripts/_test/conftest.py", "plugin/gizmoduck/pytest.ini",
                 "skills/intune-graph/pyproject.toml", "skills/notify/setup.cfg",
                 "skills/mermaid-svg-bitbucket/tox.ini", "skills/doc-builder/scripts/test_new.py",
                 "plugin/crew/tests/context.py", "plugin/crew/tests/fixtures/x_test.py"):
        got, _ = select_paths([path])
        expect(COMBINED_KEYS <= selected(got) and got["combined"] == "true"
               and got["pytest_combined"].split()[:len(SEL.COMBINED)] == list(SEL.COMBINED),
               f"{path}: can change the combined session but selected {got['pytest_combined']!r}")
    for path in ("skills/notify/scripts/notify.py", "skills/notify/SKILL.md",
                 "skills/cisco-meraki/tests/conftest.py"):
        got, _ = select_paths([path])
        expect(not COMBINED_KEYS <= selected(got),
               f"{path}: cannot change the combined session but selected all of it")


def case_combined_test_dirs_share_no_module_basename():
    # Fail fast on the collision itself: main's full run would stop with
    # "import file mismatch" while a PR's subset run passed.
    owners = {}
    for test_dir in SEL.COMBINED:
        for _base, dirs, files in os.walk(os.path.join(REPO, test_dir)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name.endswith(".py") and name != "conftest.py":
                    owners.setdefault(name, set()).add(test_dir)
    dupes = {name: sorted(dirs) for name, dirs in owners.items() if len(dirs) > 1}
    expect(not dupes, f"module basenames shared across combined test dirs: {dupes}")


SYSPATH_PLUGIN = r"""
import json, os, sys

def pytest_collection_finish(session):
    with open(os.environ["CI_SELECT_SYSPATH_OUT"], "w", encoding="utf-8") as fh:
        json.dump({"path": list(sys.path), "errors": session.testsfailed}, fh)
"""


def combined_syspath():
    """Every directory under the checkout that the full combined run has on
    sys.path once it has collected, measured by running that collection (the
    same paths and pinned config as pytest-crew.yml), not listed by hand.
    Returns (dirs, problem)."""
    runner = load(os.path.join(REPO, "scripts", "gate-runner.py"), "gate_runner")
    with tempfile.TemporaryDirectory() as tmp:
        pathlib.Path(tmp, "ci_select_syspath.py").write_text(SYSPATH_PLUGIN, encoding="utf-8")
        out = os.path.join(tmp, "syspath.json")
        env = dict(os.environ, PYTHONPATH=tmp, CI_SELECT_SYSPATH_OUT=out, PYTHONDONTWRITEBYTECODE="1")
        done = subprocess.run(
            [sys.executable, "-m", "pytest", *SEL.COMBINED, *runner.COMBINED_CONFIG, "--collect-only",
             "-q", "-p", "no:cacheprovider", "-p", "ci_select_syspath"],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=600, check=False,
            stdin=subprocess.DEVNULL)
        if not os.path.exists(out):
            return None, (f"the collection never finished (rc {done.returncode}):\n"
                          f"{done.stdout[-2000:]}{done.stderr[-2000:]}")
        with open(out, encoding="utf-8") as fh:
            data = json.load(fh)
    if done.returncode != 0 or data["errors"]:
        # A module that failed to import may not have made its sys.path
        # insert, so the measurement would be incomplete: fail, do not guess.
        return None, (f"the combined collection had errors (rc {done.returncode}), so its sys.path "
                      f"is not complete:\n{done.stdout[-3000:]}")
    root = os.path.realpath(REPO)
    dirs = []
    for entry in data["path"]:
        real = os.path.realpath(entry or os.getcwd())
        if real != root and real.startswith(root + os.sep) and os.path.isdir(real) and real not in dirs:
            dirs.append(real)
    return dirs, None


def importable_names(directory):
    """{name: kind} for the top-level names `directory` provides on sys.path:
    "module" (x.py), "package" (x/__init__.py), or "namespace" (a directory
    holding Python but no __init__.py)."""
    names, rank = {}, {"package": 2, "module": 1, "namespace": 0}

    def put(name, kind):
        # Within one directory a regular package beats a module, and both
        # beat a namespace directory: that is what `import name` finds.
        if rank[kind] >= rank.get(names.get(name), -1):
            names[name] = kind

    for entry in os.scandir(directory):
        if entry.name.startswith((".", "__pycache__")):
            continue
        if entry.is_file() and entry.name.endswith(".py") and entry.name != "conftest.py":
            put(entry.name[:-3], "module")
        elif entry.is_dir() and os.path.isfile(os.path.join(entry.path, "__init__.py")):
            put(entry.name, "package")
        elif entry.is_dir() and any(n.endswith(".py") for n in os.listdir(entry.path)):
            put(entry.name, "namespace")
    return names


def case_no_name_is_importable_from_two_combined_syspath_dirs():
    # One shared sys.path, no __init__.py and a sys.modules cache: the first
    # import of a bare name wins for every suite in the run. A PR whose subset
    # run misses the other suite passes; main's full run fails. So this case,
    # which runs on every PR, fails on the collision itself.
    dirs, problem = combined_syspath()
    if problem:
        expect(False, problem)
        return
    expect(any(d.endswith(os.path.join("intune-graph", "scripts")) for d in dirs)
           and any(d.endswith(os.path.join("crew", "hooks", "scripts")) for d in dirs),
           f"the measured sys.path lacks suites it must have: {dirs}")
    owners = {}
    for directory in dirs:
        for name, kind in importable_names(directory).items():
            owners.setdefault(name, []).append((os.path.relpath(directory, REPO), kind))
    # A module or regular package shadows every later directory's name. Two
    # namespace directories merge into one package (PEP 420), so only those
    # may share a name -- and not with a module or regular package.
    dupes = {name: where for name, where in owners.items()
             if len(where) > 1 and any(kind != "namespace" for _d, kind in where)}
    expect(not dupes, f"names importable from two directories on the combined run's sys.path "
                      f"(the first import wins for every suite): {dupes}")


def case_the_combined_run_pins_its_session_and_falls_back_to_the_whole_list():
    doc = _load_workflow("pytest-crew.yml")
    runs = [st for st in doc["jobs"]["test"]["steps"]
            if "select.outputs.combined" in _expr(st.get("if", "")) and "PYTEST_COMBINED" in str(st.get("run"))]
    expect(len(runs) == 1, f"pytest-crew.yml test: {len(runs)} combined-run steps, expected 1")
    if runs:
        run = " ".join(str(runs[0]["run"]).split())
        expect("${PYTEST_COMBINED:-" + " ".join(SEL.COMBINED) + "}" in run,
               f"the combined run does not fall back to the whole COMBINED list: {run}")
        expect("-c plugin/gizmoduck/pytest.ini --rootdir plugin/gizmoduck" in run,
               f"the combined run does not pin the session's config: {run}")


def case_lint_config_in_a_plugin_or_skill_selects_lint():
    for path in ("skills/notify/ruff.toml", "skills/notify/.ruff.toml", "plugin/localgpu/pyproject.toml",
                 "skills/aws-opensearch/.pylintrc", "plugin/rule-of-two/pylintrc",
                 "mcp-servers/pyproject.toml"):
        got, _ = select_paths([path])
        expect(got["lint"] == "true", f"{path}: lint configuration did not select lint")


# ---- must select everything ----------------------------------------------------

def case_paths_outside_every_component_select_everything():
    for path in ("scripts/check-marketplace.py", "scripts/ci-select.py", ".claude-plugin/marketplace.json",
                 ".github/workflows/pylint.yml", ".github/workflows/pytest-crew.yml", "README.md",
                 "CHANGELOG.md", "CLAUDE.md", "AGENTS.md", "plugin/PLUGINS.md", "skills/UPDATE.md",
                 "plugin/README.md", ".crew/verify.json", ".crew/codemap/crew.md",
                 ".claude/rules/x.md", ".pylintrc", "ruff.toml", "conftest.py", "requirements.txt",
                 "some-new-file.txt", "_verify/smoke.sh", "docs/guides/crew/src/config_reference.py"):
        got, out = select_paths([path])
        expect(is_all(got), f"{path}: expected everything, got {got}")
        expect("everything runs" in out and "SKIPPED" not in out,
               f"{path}: the everything line is missing or a skip was announced:\n{out}")


def case_docs_mixed_with_code_select_everything():
    got, _ = select_paths(["docs/handoff/x.md", "scripts/gate-runner.py"])
    expect(is_all(got), f"docs + scripts/: expected everything, got {got}")


def case_every_non_pull_request_event_selects_everything():
    for event in ("push", "schedule", "workflow_dispatch", "merge_group", ""):
        got, _ = select_paths(["docs/handoff/x.md"], event=event)
        expect(is_all(got), f"event {event!r}: expected everything, got {got}")


def case_an_empty_diff_selects_everything():
    got, _ = select_paths([])
    expect(is_all(got), f"an empty diff: expected everything, got {got}")


def case_an_exception_selects_everything():
    # --paths-from naming a missing file raises inside decide(): fail closed.
    rc, out, _ = run(["--event", "pull_request", "--paths-from", "/nonexistent/ci-select/paths"])
    got = parse(out)
    expect(rc == 0 and is_all(got) and "::warning::" in out,
           f"an exception: expected rc 0, everything and a warning; got rc {rc}:\n{out}")


def case_an_unwritable_output_fails_the_step():
    rc, _, err = run(["--event", "push", "--output", "/nonexistent/dir/out"])
    expect(rc == 1 and "could not write" in err, f"unwritable --output: rc {rc}, stderr {err!r}")


def case_output_is_appended_not_truncated():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "github_output")
        pathlib.Path(out).write_text("earlier=kept\n", encoding="utf-8")
        rc, _, _ = run(["--event", "push", "--output", out])
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
    expect(rc == 0 and text.startswith("earlier=kept\n") and "\nall=true\n" in text,
           f"--output was not appended to: rc {rc}, {text!r}")


# ---- real git diffs -----------------------------------------------------------

def git(cwd, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env,
                          timeout=TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise AssertionError(f"git {args}: {done.stderr}")
    return done.stdout


def merge_repo(tmp, changes, renames=()):
    """A repo whose HEAD is a merge of a PR branch carrying `changes` (path ->
    text) and `renames` (old, new) into main, like refs/pull/N/merge."""
    git(tmp, "init", "-q", "-b", "main")
    for path in ["plugin/crew/hooks/x.py", "docs/a.md"] + [old for old, _ in renames]:
        os.makedirs(os.path.join(tmp, os.path.dirname(path)), exist_ok=True)
        pathlib.Path(tmp, path).write_text("base\n", encoding="utf-8")
    git(tmp, "add", "-A")
    git(tmp, "commit", "-q", "-m", "base")
    git(tmp, "checkout", "-q", "-b", "pr")
    for path, text in changes.items():
        os.makedirs(os.path.join(tmp, os.path.dirname(path) or "."), exist_ok=True)
        pathlib.Path(tmp, path).write_text(text, encoding="utf-8")
    for old, new in renames:
        os.makedirs(os.path.join(tmp, os.path.dirname(new)), exist_ok=True)
        git(tmp, "mv", old, new)
    git(tmp, "add", "-A")
    git(tmp, "commit", "-q", "-m", "pr")
    git(tmp, "checkout", "-q", "main")
    pathlib.Path(tmp, "base-moved.txt").write_text("main moved on\n", encoding="utf-8")
    git(tmp, "add", "-A")
    git(tmp, "commit", "-q", "-m", "main moves")
    git(tmp, "merge", "-q", "--no-ff", "-m", "merge pr", "pr")


def case_a_real_docs_only_merge_skips():
    with tempfile.TemporaryDirectory() as tmp:
        merge_repo(tmp, {"docs/handoff/new.md": "x\n"})
        rc, out, _ = run(["--event", "pull_request"], cwd=tmp)
    got = parse(out)
    expect(rc == 0 and got.get("all") == "false" and selected(got) == set(),
           f"a docs-only merge commit: rc {rc}, got {got}\n{out}")


def case_a_real_component_merge_selects_it_and_ignores_the_base_side():
    # main's own commit (base-moved.txt, outside every component) is NOT the
    # PR's change: the diff is against the first parent, the base tip.
    with tempfile.TemporaryDirectory() as tmp:
        merge_repo(tmp, {"plugin/gizmoduck/scripts/x.py": "x\n"})
        rc, out, _ = run(["--event", "pull_request"], cwd=tmp)
    got = parse(out)
    expect(rc == 0 and got.get("all") == "false" and selected(got) == {"gizmoduck"},
           f"a gizmoduck merge commit: rc {rc}, got {got}\n{out}")


def case_a_rename_out_of_a_component_selects_that_component():
    with tempfile.TemporaryDirectory() as tmp:
        merge_repo(tmp, {}, renames=(("skills/notify/scripts/old.md", "docs/moved.md"),))
        rc, out, _ = run(["--event", "pull_request"], cwd=tmp)
    got = parse(out)
    expect(rc == 0 and "notify" in selected(got),
           f"a rename out of skills/notify/ did not select notify: {got}\n{out}")


def case_a_diff_error_selects_everything():
    with tempfile.TemporaryDirectory() as tmp:
        merge_repo(tmp, {"docs/handoff/new.md": "x\n"})
        rc, out, _ = run(["--event", "pull_request", "--base", "no-such-ref"], cwd=tmp)
    got = parse(out)
    expect(rc == 0 and is_all(got) and "::warning::" in out and "failed" in out,
           f"a diff error: expected everything and a warning; rc {rc}:\n{out}")


def case_a_head_that_is_not_a_merge_selects_everything():
    with tempfile.TemporaryDirectory() as tmp:
        merge_repo(tmp, {"docs/handoff/new.md": "x\n"})
        rc, out, _ = run(["--event", "pull_request", "--head", "HEAD^1", "--base", "HEAD^1^1"],
                         cwd=tmp)
    got = parse(out)
    expect(rc == 0 and is_all(got) and "not a merge commit" in out,
           f"a non-merge head: expected everything; rc {rc}:\n{out}")


def case_outside_a_git_repository_selects_everything():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out, _ = run(["--event", "pull_request"], cwd=tmp)
    expect(rc == 0 and is_all(parse(out)), f"no repository: expected everything; rc {rc}:\n{out}")


# ---- the wiring -----------------------------------------------------------------

def case_combined_list_matches_the_gate_runner_table():
    runner = load(os.path.join(REPO, "scripts", "gate-runner.py"), "gate_runner")
    expect(tuple(runner.COMBINED_DIRS) == tuple(SEL.COMBINED),
           f"gate-runner COMBINED_DIRS {runner.COMBINED_DIRS} != ci-select COMBINED {SEL.COMBINED}")


def case_every_component_root_and_test_dir_exists():
    for key, root, test_dir in SEL.COMPONENTS:
        expect(os.path.isdir(os.path.join(REPO, root)), f"{key}: component root {root} is missing")
        if test_dir:
            expect(os.path.isdir(os.path.join(REPO, test_dir)), f"{key}: test dir {test_dir} is missing")
    for _glob, target in SEL.READERS:
        if target.startswith("plugin/crew/tests/"):
            expect(os.path.isfile(os.path.join(REPO, target)), f"READERS names missing {target}")
        else:
            expect(target in KEYS, f"READERS names unknown component {target}")


KNOWN_OUTPUTS = set(KEYS) | {"combined", "lint", "all"}
_TERM = r"(?:steps|needs)\.select\.outputs\.([a-z_]+) != 'false'"
# The whole `if:` of a gated suite step must be one of these shapes, so that
# a missing output (a failed or skipped select) runs the suite. Matching the
# whole expression, not a token in it: `... != 'false' && false` fails.
SUITE_IF = (
    re.compile(rf"^{_TERM}$"),
    re.compile(rf"^env\.RUN_LEG == 'true' && {_TERM}$"),
    re.compile(rf"^env\.RUN_LEG == 'true' && \({_TERM}(?: \|\| {_TERM})+\)$"),
)
NOTICE_IF = re.compile(r"^(?:steps|needs)\.select\.outputs\.([a-z_]+) == 'false'$")
JOB_IF_AFTER_SELECT = ("!cancelled()", "always()")


def _expr(value):
    text = " ".join(str(value).split())
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2].strip()
    return text


def _load_workflow(name):
    import yaml  # pylint: disable=import-outside-toplevel
    with open(os.path.join(REPO, ".github", "workflows", name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _gate_problems(wf, doc):
    """Every gate in one parsed workflow that could skip a suite when the
    selection is missing, as one message each."""
    problems, gates = [], 0
    for job_id, job in doc["jobs"].items():
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        if "select" in needs and _expr(job.get("if", "")) not in JOB_IF_AFTER_SELECT:
            problems.append(f"{wf} jobs.{job_id}: needs select but its if is "
                            f"{job.get('if')!r}; without !cancelled() or always() a failed "
                            "select skips the required legs, and skipped reads as passed")
        if "select.outputs" in _expr(job.get("if", "")):
            problems.append(f"{wf} jobs.{job_id}: a job-level if on the selection skips a "
                            "required check")
        for i, step in enumerate(job.get("steps") or []):
            cond = _expr(step.get("if", ""))
            if "select.outputs" not in cond:
                continue
            gates += 1
            where = f"{wf} jobs.{job_id}.steps[{i}] ({step.get('name', step.get('uses'))})"
            notice = NOTICE_IF.match(cond)
            if notice:
                keys = [notice.group(1)]
                run = " ".join(str(step.get("run", "")).split())
                if not (run.startswith('echo "::notice::') and "SKIPPED, not passed" in run
                        and "&&" not in run and ";" not in run):
                    problems.append(f"{where}: an == 'false' gate may only print the SKIPPED notice")
            else:
                shape = next((m for m in (rx.match(cond) for rx in SUITE_IF) if m), None)
                if not shape:
                    problems.append(f"{where}: `if: {cond}` is not a fail-open gate shape")
                    continue
                keys = re.findall(r"select\.outputs\.([a-z_]+)", cond)
            for key in keys:
                if key not in KNOWN_OUTPUTS:
                    problems.append(f"{where}: gates on unknown output {key!r} (always empty)")
    problems += _reads_outside_if(wf, doc)
    if not gates:
        problems.append(f"{wf}: no step is gated on the selection")
    return problems


def _walk(node, path):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, path + (str(i),))
    else:
        yield path, node


def _reads_outside_if(wf, doc):
    """A selection read anywhere but an `if:` escapes the gate-shape check
    (a `run:` could test it any way it likes). Allowed besides `if:`: the
    combined run's PYTEST_COMBINED env, and a select job's `outputs:`
    forwarding its own step's value."""
    problems = []
    for path, value in _walk(doc.get("jobs", {}), ("jobs",)):
        if "select.outputs" not in str(value) or path[-1] == "if":
            continue
        if path[-2:] == ("env", "PYTEST_COMBINED") and \
                _expr(value) == "steps.select.outputs.pytest_combined":
            continue
        if len(path) == 4 and path[1] == "select" and path[2] == "outputs" and \
                _expr(value) == f"steps.select.outputs.{path[3]}":
            continue
        problems.append(f"{wf} {'.'.join(path)}: reads the selection outside an if: ({value!r})")
    return problems


def case_workflows_gate_on_real_keys_and_fail_open_to_running():
    for wf in WORKFLOWS:
        with open(os.path.join(REPO, ".github", "workflows", wf), encoding="utf-8") as fh:
            text = fh.read()
        expect("python3 scripts/ci-select.py --event \"${{ github.event_name }}\" --output "
               "\"$GITHUB_OUTPUT\"" in text, f"{wf}: does not run ci-select.py the standard way")
        for problem in _gate_problems(wf, _load_workflow(wf)):
            expect(False, problem)
    for wf in NEVER_SELECTED:
        path = os.path.join(REPO, ".github", "workflows", wf)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            expect("ci-select.py --event" not in body and "select.outputs" not in body,
                   f"{wf} must always run, but is gated on ci-select")


def crew_files(got):
    return {p for p in got["pytest_combined"].split() if p.startswith(CREW + "test_")}


def case_readers_select_the_crew_files_and_suites_that_read_the_path():
    rows = (
        # (path, the keys it must select exactly, crew files it must select)
        ("plugin/gizmoduck/scripts/routine.py", {"gizmoduck"},
         {CREW + "test_tool_resolution.py", CREW + "test_sendkeys_structural_gate.py"}),
        ("skills/cisco-meraki/tests/test_new.py", {"cisco_meraki"},
         {CREW + "test_pwsh_cache_isolation.py"}),
        ("skills/aws-opensearch/scripts/x.py", set(), {CREW + "test_tool_resolution.py"}),
        ("skills/doc-builder/scripts/build_report.py", {"doc_builder"},
         {CREW + "test_docs_routing.py", CREW + "test_sabotage_harness.py"}),
        ("skills/bitbucket/scripts/merge_gate.sh", {"bitbucket"},
         {CREW + "test_gate_command.py", CREW + "test_promote_merge_gate.py",
          CREW + "test_sabotage_harness.py"}),
        ("skills/github/scripts/merge_gate.sh", set(), {CREW + "test_gate_command.py"}),
        ("skills/solomon-doc-builder/assets/brand.json", {"doc_builder"}, set()),
        ("skills/solomon-doc-builder/assets/logo/solomon-logo-on-dark.png", {"doc_builder"}, set()),
        ("skills/some-new-brand/assets/brand.json", {"doc_builder"}, set()),
        ("plugin/crew/hooks/scripts/role-write-guard.ps1", {"crew", "obsidian_vault"}, set()),
        ("docs/guides/crew/src/auto-cycle.md", set(),
         {CREW + "test_crew_autopilot_policy.py", CREW + "test_crew_resume.py",
          CREW + "test_crew_train.py", CREW + "test_status_vocabulary.py",
          CREW + "test_troubleshooting_guide.py"} | DOC_SCAN),
        ("skills/aws-opensearch/SKILL.md", set(), DOC_SCAN),
    )
    for path, keys, files in rows:
        got, _ = select_paths([path])
        expect(selected(got) == keys, f"{path}: selected {selected(got)}, expected {keys}")
        expect(got["all"] == "false", f"{path}: selected everything")
        if "crew" not in keys:
            expect(files <= crew_files(got), f"{path}: crew files {crew_files(got)} lack {files - crew_files(got)}")
    got, _ = select_paths(["skills/aws-opensearch/SKILL.md"])
    expect(got["lint"] == "false" and crew_files(got) == DOC_SCAN,
           f"an untested skill's SKILL.md selected more than the doc scans: {got}")


def case_every_path_selects_the_whole_tree_scan():
    for path in ("plugin/gizmoduck/bootstrap.sh", "mcp-servers/packages/core/src/index.ts",
                 "skills/aws-opensearch/references/x.json", "docs/handoff/x.md"):
        got, _ = select_paths([path])
        expect(CREW + "test_sendkeys_structural_gate.py" in crew_files(got),
               f"{path}: test_sendkeys_structural_gate.py reads every tracked file but was not selected")


def case_a_crew_file_target_has_no_slow_or_wallclock_test():
    # The combined run is `-m "not wallclock"` and crew's conftest drops
    # `slow` from it: a file named alone must have neither, or part of it
    # would never run for the change that selected it.
    marker = re.compile(r"mark\.(slow|wallclock)\b|\bSLOW\b|pytestmark")
    for _glob, target in SEL.READERS:
        if target.startswith(CREW):
            with open(os.path.join(REPO, target), encoding="utf-8") as fh:
                expect(not marker.search(fh.read()), f"{target} has a slow/wallclock test")


CASES = [(name[len("case_"):], fn) for name, fn in sorted(globals().items())
         if name.startswith("case_")]


def main() -> int:
    passed = failed = 0
    for name, fn in CASES:
        before = len(FAILURES)
        try:
            fn()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            FAILURES.append(f"{name} raised {type(exc).__name__}: {exc}")
        new = FAILURES[before:]
        if new:
            failed += 1
            print(f"  FAIL {name}")
            for msg in new:
                print("       " + msg.replace("\n", "\n       "))
        else:
            passed += 1
            print(f"  ok   {name}")
    print(f"\nci-select: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
