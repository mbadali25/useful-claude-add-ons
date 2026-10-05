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


OUTPUT_REF = re.compile(r"(?:steps|needs)\.select\.outputs\.([A-Za-z0-9_-]+)\s*(==|!=)\s*'([^']*)'")


def case_workflows_gate_on_real_keys_and_fail_open_to_running():
    known = set(KEYS) | {"pytest_combined", "lint", "all"}
    for wf in WORKFLOWS:
        with open(os.path.join(REPO, ".github", "workflows", wf), encoding="utf-8") as fh:
            text = fh.read()
        expect("python3 scripts/ci-select.py --event \"${{ github.event_name }}\" --output "
               "\"$GITHUB_OUTPUT\"" in text, f"{wf}: does not run ci-select.py the standard way")
        refs = OUTPUT_REF.findall(text)
        expect(refs, f"{wf}: no step is gated on the selection")
        for key, op, value in refs:
            expect(key in known, f"{wf}: gates on unknown output {key!r} (always empty)")
            # A suite step must RUN when the output is missing: `!= 'false'`.
            # Only a notice step may test `== 'false'`; pytest_combined is a list.
            ok = (op, value) in ((("!=", "false"), ("==", "false")) if key != "pytest_combined"
                                 else (("!=", ""),))
            expect(ok, f"{wf}: `{key} {op} '{value}'` does not fail open to running the suite")
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
        ("skills/notify/tests/test_new.py", {"notify"}, {CREW + "test_pwsh_cache_isolation.py"}),
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
