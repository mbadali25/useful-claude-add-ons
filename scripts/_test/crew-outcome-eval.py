#!/usr/bin/env python3
"""Suite for scripts/crew-outcome-eval.py (L-0728).

No model is called and nothing billed runs. Every case builds a throwaway source
repository, a fixture task, tmp `HOME`, `CLAUDE_CONFIG_DIR` and `CODEX_HOME`
(holding fake auth files), and puts a stub `docker` first on PATH. The stub
docker records its argv and runs a stub `claude` in the mounted run directories,
so the harness sees real files, real git repositories and real pytest runs.

What this suite proves and what it cannot: the harness's mounts, network,
refresh-token stripping, grading, cost arithmetic, budget rule and verdict rule.
That the container really hides the host checkout, the task store and earlier
runs, and really blocks github.com, is proved only by the real-container canary
(evals/crew-outcome/container/canary.sh, run by hand; its output is kept with
the results). A stub docker cannot hide a host path.

Must-block and must-allow cases come in pairs; sabotage notes are in the PR.

Run: python3 scripts/_test/crew-outcome-eval.py
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "scripts", "crew-outcome-eval.py")
REAL_EVAL_DIR = os.path.join(REPO, "evals", "crew-outcome")

spec = importlib.util.spec_from_file_location("crew_outcome_eval", SCRIPT)
eval_mod = importlib.util.module_from_spec(spec)
sys.modules["crew_outcome_eval"] = eval_mod
spec.loader.exec_module(eval_mod)

UNKNOWN = "UNKNOWN"

DOCKER_STUB = '''#!PYTHON
import json, os, subprocess, sys
argv = sys.argv[1:]
with open(os.environ.get("STUB_DOCKER_LOG", os.devnull), "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")
if argv[:2] == ["network", "inspect"]:
    print("127.0.0.1")
    sys.exit(0)
if argv[:1] == ["run"] and "--rm" in argv:
    mounts = {}
    env = dict(os.environ)
    i = 0
    while i < len(argv):
        if argv[i] == "-v":
            src, dst = argv[i + 1].split(":")[:2]
            mounts[dst] = src
        if argv[i] == "-e":
            k, _, v = argv[i + 1].partition("=")
            env[k] = v
        i += 1
    inner = argv[argv.index("crew-outcome-eval:1") + 1:]
    if inner and inner[0] == "/opt/eval-shim/eval-run":
        inner = inner[1:]
    if "/run/home" in mounts:
        env["HOME"] = mounts["/run/home"]
        env["CLAUDE_CONFIG_DIR"] = mounts["/run/home"] + "/.claude"
        env["CODEX_HOME"] = mounts["/run/home"] + "/.codex"
    if inner[0] == "/usr/local/bin/claude":
        inner[0] = os.environ["STUB_CLAUDE"]
    elif "/run/home" in mounts:
        inner = [part.replace("/run/home", mounts["/run/home"]) for part in inner]
    sys.exit(subprocess.run(inner, cwd=mounts["/run/repo"], env=env, check=False).returncode)
sys.exit(0)
'''

CLAUDE_STUB = '''#!PYTHON
import json, os, sys, time
mode = os.environ.get("STUB_MODE", "ok")
state = os.environ["STUB_STATE"]
count = 1
if os.path.exists(state):
    count = int(open(state).read()) + 1
open(state, "w").write(str(count))
failing = (mode == "fail-first" and count == 1) or (mode == "fail-second" and count == 2) or mode == "always-fail"
argv = sys.argv[1:]
resumed = argv[argv.index("--resume") + 1] if "--resume" in argv else None
sid = resumed or "sess-%d" % count
calls_file = state + "." + sid
calls = int(open(calls_file).read()) + 1 if os.path.exists(calls_file) else 1
open(calls_file, "w").write(str(calls))
config = os.environ["CLAUDE_CONFIG_DIR"]
proj = os.path.join(config, "projects", "-run-repo")
os.makedirs(proj, exist_ok=True)
def rec(mid, out):
    return {"type": "assistant", "timestamp": "2026-10-19T00:00:00Z", "isSidechain": False,
            "message": {"id": mid, "model": "claude-sonnet-5-5",
                        "usage": {"input_tokens": 1000, "output_tokens": out,
                                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}
lines = [rec("m%d" % count, 1000)]
if mode == "subagent-missing":
    lines.append({"type": "user", "toolUseResult": {"agentId": "ghost"}})
open(os.path.join(proj, sid + ".jsonl"), "a").write("\\n".join(json.dumps(r) for r in lines) + "\\n")
if mode == "mentions-reference":
    open(os.path.join(proj, sid + ".jsonl"), "a").write(json.dumps({"type": "user", "text": os.environ["STUB_SHA"]}) + "\\n")
if failing:
    print("boom")
    sys.exit(3)
if mode == "error-json":
    print(json.dumps({"type": "result", "is_error": True, "session_id": sid, "result": "something odd", "total_cost_usd": 0.1}))
    sys.exit(1)
if mode in ("ok", "mentions-reference", "subagent-missing", "fail-first", "fail-second", "exit3-ok-json", "no-session-id"):
    with open("calc.py", "a") as fh:
        fh.write("\\n\\ndef mul(a, b):\\n    return a * b\\n")
payload = {"type": "result", "is_error": False, "session_id": sid,
           "result": os.environ.get("STUB_RESULT", "done"), "total_cost_usd": 0.5 * calls}
if mode == "no-session-id":
    del payload["session_id"]
print(json.dumps(payload))
if mode == "exit3-ok-json":
    sys.exit(3)
'''


def slurp(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def sh(*argv, cwd=None):
    out = subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"{argv}: {out.stderr}")
    return out.stdout.strip()


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    if mode:
        os.chmod(path, mode)


EXEC = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH

CALC_BASE = "def add(a, b):\n    return a + b\n"
VISIBLE_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
LONG1 = "    assert mul(7, 6) == 42, 'multiplication must return the exact product of its two arguments'"
LONG2 = "    assert mul(-2, 3) == -6, 'distinctive hidden content about negative operands in multiplication'"
LONG3 = "    assert mul(0, 5) == 0, 'zero times anything is zero, a distinctive hidden check line right here'"
HIDDEN_TEST = ("from calc import add, mul\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\n"
               "def test_mul():\n    assert mul(2, 3) == 6\n" + LONG1 + "\n\n\n"
               "def test_mul_zero():\n    assert mul(0, 5) == 0\n" + LONG3 + "\n\n\n"
               "def test_mul_neg_distinctive_line_xyz():\n    assert mul(-2, 3) == -6\n" + LONG2 + "\n")
CONFTEST = "import sys, os\nsys.path.insert(0, os.getcwd())\n"


class Fix:
    """A source repo (base, reference), a fixture task, tmp homes, stub bin."""

    def __init__(self, tmp, hidden_passes_at_base=False, reference_broken=False):
        self.tmp = tmp
        self.src = os.path.join(tmp, "src")
        os.makedirs(self.src)
        sh("git", "init", "-q", "-b", "main", cwd=self.src)
        write(os.path.join(self.src, "calc.py"), CALC_BASE)
        write(os.path.join(self.src, "conftest.py"), CONFTEST)
        write(os.path.join(self.src, "tests", "test_calc.py"), VISIBLE_TEST)
        write(os.path.join(self.src, "README.md"), "see https://github.com/mbadali25/useful-claude-add-ons\n")
        self.commit("base")
        self.base = sh("git", "rev-parse", "HEAD", cwd=self.src)
        write(os.path.join(self.src, "calc.py"),
              CALC_BASE + ("\n\ndef mul(a, b):\n    return a + b\n" if reference_broken
                           else "\n\ndef mul(a, b):\n    return a * b\n"))
        self.commit("reference")
        self.reference = sh("git", "rev-parse", "HEAD", cwd=self.src)
        self.task_root = os.path.join(tmp, "tasks")
        self.task_dir = os.path.join(self.task_root, "t1")
        hidden = HIDDEN_TEST if not hidden_passes_at_base else HIDDEN_TEST.replace("mul(2, 3) == 6", "True")
        if hidden_passes_at_base:
            hidden = ("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n\n\n"
                      "def test_mul():\n    assert True\n\n\ndef test_mul_zero():\n    assert True\n\n\n"
                      "def test_mul_neg_distinctive_line_xyz():\n    assert True\n")
        write(os.path.join(self.task_dir, "grading", "tests", "test_calc.py.frozen"), hidden)
        write(os.path.join(self.task_dir, "grading", "conftest.py.frozen"), CONFTEST)
        write(os.path.join(self.task_dir, "statement.md"), "Add a mul(a, b) function to calc.py.\n")
        self.task = {
            "name": "t1", "ticket": "L-9999", "repo": "x/y", "base": self.base, "reference": self.reference,
            "bucket": "S", "referenceLines": 3, "statementFile": "statement.md",
            "defects": {"multiplies": ["tests/test_calc.py::test_mul", "tests/test_calc.py::test_mul_zero"],
                        "negatives": ["tests/test_calc.py::test_mul_neg_distinctive_line_xyz"]},
            "regressionInventory": ["tests/test_calc.py::test_add"],
            "gradingFiles": ["tests/test_calc.py", "conftest.py"],
            "testCommand": ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rA", "tests/test_calc.py"],
            "referencePr": 4242,
        }
        write(os.path.join(self.task_dir, "task.json"), json.dumps(self.task))
        self.home = os.path.join(tmp, "home")
        self.claude_home = os.path.join(tmp, "claude-config")
        self.codex_home = os.path.join(tmp, "codex-home")
        write(os.path.join(self.claude_home, ".credentials.json"), json.dumps(
            {"claudeAiOauth": {"accessToken": "AT", "refreshToken": "RT-SECRET", "expiresAt": 9999999999999},
             "mcpOAuth": {"x": {"accessToken": "MCP-SECRET"}}}))
        write(os.path.join(self.codex_home, "auth.json"), json.dumps(
            {"auth_mode": "chatgpt", "OPENAI_API_KEY": "KEY-SECRET", "last_refresh": "2026-10-20T00:00:00Z",
             "tokens": {"access_token": "AT", "refresh_token": "RT-SECRET", "id_token": "ID",
                        "extra": "EXTRA-SECRET"}}))
        write(os.path.join(self.home, "owner-secret.txt"), "SECRET-OWNER-FILE")
        self.bin = os.path.join(tmp, "bin")
        write(os.path.join(self.bin, "docker"), DOCKER_STUB.replace("#!PYTHON", "#!" + sys.executable), EXEC)
        write(os.path.join(self.bin, "stub-claude"), CLAUDE_STUB.replace("#!PYTHON", "#!" + sys.executable), EXEC)
        self.docker_log = os.path.join(tmp, "docker.jsonl")
        self.env = {"PATH": self.bin + os.pathsep + os.environ.get("PATH", ""), "HOME": self.home,
                    "CLAUDE_CONFIG_DIR": self.claude_home, "CODEX_HOME": self.codex_home,
                    "STUB_DOCKER_LOG": self.docker_log, "STUB_CLAUDE": os.path.join(self.bin, "stub-claude"),
                    "STUB_STATE": os.path.join(tmp, "stub-state"), "STUB_SHA": self.reference,
                    "TMPDIR": tmp,
                    # a root test run owns nothing the harness chowned to uid 1000 for the container
                    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"}
        self.runs = os.path.join(tmp, "runs")
        self.results = os.path.join(tmp, "results", "results.jsonl")
        os.makedirs(os.path.dirname(self.results))
        self.arm = {
            "arm": "baseline", "author": {"model": "claude-sonnet-5-5", "effort": "high"},
            "reviewer": {"model": "claude-sonnet-5-5", "effort": "high"},
            "wallClockMinutes": {"S": 60, "M": 120, "L": 240}, "settings": {},
            "cli": {"args": ["--dangerously-skip-permissions"], "maxCycles": 3, "maxResumes": 2,
                    "terminalRegex": "STOP"},
            "prompts": {"implement": "{statement}", "review": "/code-review", "fix": "{findings}",
                        "start": "{statement}", "resume": "continue"},
            "reviewParse": {"findings": "^FINDING", "noFindings": "^No findings"},
            "proxyIgnoreHosts": ["telemetry.example"],
        }

    def commit(self, message):
        sh("git", "add", "-A", cwd=self.src)
        sh("git", "-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-q", "-m", message, cwd=self.src)

    def ctx(self):
        container = os.path.join(self.tmp, "container")
        os.makedirs(container, exist_ok=True)
        for name in ("proxy.py", "proxy-allowlist.txt"):
            shutil.copyfile(os.path.join(REAL_EVAL_DIR, "container", name), os.path.join(container, name))
        return {"docker": os.path.join(self.bin, "docker"), "source_repo": self.src,
                "runs_dir": self.runs,
                "results": self.results, "crew_plugin": os.path.join(REPO, "plugin", "crew"),
                "container_dir": container, "env": self.env}

    def load(self):
        return eval_mod.load_task(self.task_dir)


@contextlib.contextmanager
def patched_env(env):
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def refused(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except eval_mod.EvalError as exc:
        return str(exc)
    return None


# --------------------------------------------------------------------------
# validate

def case_validate_accepts_a_good_task(tmp):
    fix = Fix(tmp)
    problems = eval_mod.validate_task(fix.load(), fix.src)
    return problems == [], problems


def case_validate_refuses_hidden_tests_that_pass_at_base(tmp):
    fix = Fix(tmp, hidden_passes_at_base=True)
    problems = eval_mod.validate_task(fix.load(), fix.src)
    return any("hidden tests pass at base" in p for p in problems), problems


def case_validate_refuses_hidden_tests_that_fail_at_reference(tmp):
    fix = Fix(tmp, reference_broken=True)
    problems = eval_mod.validate_task(fix.load(), fix.src)
    return any("tests fail at reference" in p for p in problems), problems


def case_validate_refuses_an_unreachable_reference_sha(tmp):
    fix = Fix(tmp)
    task = fix.load()
    task["reference"] = "0" * 40
    problems = eval_mod.validate_task(task, fix.src)
    return any("is not a commit" in p for p in problems), problems


def case_load_refuses_overlapping_defects(tmp):
    fix = Fix(tmp)
    fix.task["defects"]["negatives"].append("tests/test_calc.py::test_mul")
    write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
    message = refused(fix.load)
    return bool(message and "must not overlap" in message), message


# --------------------------------------------------------------------------
# isolation

def case_run_repo_is_one_commit_without_the_reference(tmp):
    fix = Fix(tmp)
    run = eval_mod.prepare_run(fix.load(), fix.arm, fix.src, fix.runs, 1, os.path.join(tmp, "plugin-crew"), fix.env)
    count = sh("git", "rev-list", "--count", "HEAD", cwd=run["repo"])
    reachable = eval_mod.reference_reachable(run["repo"], fix.reference)
    base_reachable = eval_mod.reference_reachable(run["repo"], fix.base)
    return count == "1" and not reachable and not base_reachable, (count, reachable, base_reachable)


def case_remove_paths_deletes_from_the_run_repo_and_refuses_an_escape(tmp):
    fix = Fix(tmp)
    arm = dict(fix.arm, removePaths=["gone-dir", "gone.txt"])
    base = os.path.join(tmp, "tree")
    os.makedirs(os.path.join(base, "gone-dir"))
    write(os.path.join(base, "gone-dir", "a.md"), "x")
    write(os.path.join(base, "gone.txt"), "x")
    write(os.path.join(base, "keep.txt"), "x")
    eval_mod.remove_arm_paths(base, arm["removePaths"])
    left = sorted(os.listdir(base))
    outside = os.path.join(tmp, "outside")
    write(outside, "x")
    message = refused(eval_mod.remove_arm_paths, base, ["../outside"])
    return left == ["keep.txt"] and os.path.exists(outside) and bool(message and "outside" in message), (left, message)


def case_remove_paths_refuses_a_prefix_sibling_a_symlink_escape_and_bad_entries(tmp):
    base = os.path.join(tmp, "tree")
    sibling = base + "-evil"
    os.makedirs(base)
    os.makedirs(sibling)
    write(os.path.join(sibling, "victim.txt"), "x")
    outside = os.path.join(tmp, "outside-dir")
    os.makedirs(outside)
    write(os.path.join(outside, "victim.txt"), "x")
    os.symlink(outside, os.path.join(base, "link"))
    os.symlink(sibling, os.path.join(base, "link-evil"))
    results = {}
    for entry in ("../tree-evil", "link/victim.txt", "link-evil/victim.txt", "", ".", "a\\b", "..\\x", "/etc"):
        results[entry] = refused(eval_mod.remove_arm_paths, base, [entry])
    survived = os.path.exists(os.path.join(sibling, "victim.txt")) and os.path.exists(os.path.join(outside, "victim.txt"))
    return survived and all(results.values()), (survived, results)


def case_remove_paths_removes_a_symlink_inside_the_repo_without_following_it(tmp):
    base = os.path.join(tmp, "tree")
    os.makedirs(os.path.join(base, "real"))
    write(os.path.join(base, "real", "a.txt"), "x")
    os.symlink("real", os.path.join(base, "alias"))
    eval_mod.remove_arm_paths(base, ["alias"])
    return sorted(os.listdir(base)) == ["real"] and os.path.exists(os.path.join(base, "real", "a.txt")), os.listdir(base)


def case_prepare_refuses_when_the_reference_is_reachable(tmp):
    fix = Fix(tmp)
    task = fix.load()
    original = eval_mod.reference_reachable
    eval_mod.reference_reachable = lambda repo, sha: True
    try:
        message = refused(eval_mod.prepare_run, task, fix.arm, fix.src, fix.runs, 1, os.path.join(tmp, "p"), fix.env)
    finally:
        eval_mod.reference_reachable = original
    return bool(message and "reachable" in message), message


def case_hidden_tests_are_absent_during_the_arm(tmp):
    fix = Fix(tmp)
    run = eval_mod.prepare_run(fix.load(), fix.arm, fix.src, fix.runs, 1, os.path.join(tmp, "plugin-crew"), fix.env)
    text = slurp(os.path.join(run["repo"], "tests", "test_calc.py"))
    return "test_mul" not in text and text == VISIBLE_TEST, text


def case_auth_files_carry_no_refresh_token_and_nothing_else_of_the_owners(tmp):
    fix = Fix(tmp)
    run = eval_mod.prepare_run(fix.load(), fix.arm, fix.src, fix.runs, 1, os.path.join(tmp, "plugin-crew"), fix.env)
    blob = ""
    for here, _dirs, names in os.walk(run["dir"]):
        if os.sep + ".git" in here:
            continue
        for name in names:
            blob += slurp(os.path.join(here, name))
    ok = ("RT-SECRET" not in blob and "MCP-SECRET" not in blob and "SECRET-OWNER-FILE" not in blob
          and "KEY-SECRET" not in blob and "EXTRA-SECRET" not in blob and "2026-10-20T00:00:00Z" in blob
          and '"accessToken": "AT"' in blob and '"access_token": "AT"' in blob and "WebFetch" in blob)
    return ok, [w for w in ("RT-SECRET", "MCP-SECRET", "SECRET-OWNER-FILE", "KEY-SECRET", "EXTRA-SECRET") if w in blob]


def case_docker_argv_mounts_only_the_run_dirs(tmp):
    fix = Fix(tmp)
    run = {"repo": "/r/run1/repo", "home": "/r/run1/home", "proxylog": "/r/run1/proxylog", "dir": "/r/run1",
           "proxysock": "/r/run1/proxysock"}
    argv = eval_mod.arm_docker_argv("/usr/bin/docker", run, "n", ("1000", "1000"), ["/usr/local/bin/claude"])
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    sources = [m.split(":")[0] for m in mounts]
    forbidden = [fix.src, REPO, fix.task_root, os.path.join(tmp, "runs", "earlier")]
    clean = not any(os.path.commonpath([s, f]) == f for s in sources for f in forbidden if f.startswith("/"))
    ok = (sources == ["/r/run1/repo", "/r/run1/home", "/r/run1/proxysock"] and clean and "--privileged" not in argv
          and argv[argv.index("--network") + 1] == "none" and "HTTPS_PROXY=http://127.0.0.1:3128" in argv
          and "ALL" in argv and argv[argv.index("crew-outcome-eval:1") + 1] == "/opt/eval-shim/eval-run")
    return ok, mounts


# --------------------------------------------------------------------------
# grading

def graded(fix, mutate=None):
    task = fix.load()
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
    write(os.path.join(run["repo"], "calc.py"), CALC_BASE + "\n\ndef mul(a, b):\n    return a * b\n")
    if mutate:
        mutate(run["repo"])
    return eval_mod.grade(task, run["repo"], fix.src)


def case_grading_scores_a_correct_run_with_no_escapes(tmp):
    result = graded(Fix(tmp))
    return result["escapedDefects"] == 0 and result["regressionTestsFailed"] == 0, result


def case_grading_counts_a_defect_when_any_of_its_tests_fail(tmp):
    def break_mul(repo):
        write(os.path.join(repo, "calc.py"),
              CALC_BASE + "\n\ndef mul(a, b):\n    return 6 if (a, b) == (2, 3) else a + b\n")
    result = graded(Fix(tmp), break_mul)
    return result["escapedDefects"] == 2 and result["defectsTotal"] == 2, result


def case_a_hidden_file_that_cannot_import_does_not_fail_the_visible_tests(tmp):
    fix = Fix(tmp)
    task = fix.load()
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(tmp, "plugin-crew"), fix.env)
    result = eval_mod.grade(task, run["repo"], fix.src)
    return result["escapedDefects"] == 2 and result["regressionTestsFailed"] == 0, result


def case_an_edited_conftest_is_restored_for_grading(tmp):
    def poison(repo):
        write(os.path.join(repo, "conftest.py"),
              "import pytest\n\n\ndef pytest_collection_modifyitems(items):\n    items.clear()\n")
    result = graded(Fix(tmp), poison)
    return result["escapedDefects"] == 0 and result["regressionTestsFailed"] == 0, result


def case_a_deleted_visible_test_is_restored_for_grading(tmp):
    def delete(repo):
        os.remove(os.path.join(repo, "tests", "test_calc.py"))
    result = graded(Fix(tmp), delete)
    return result["regressionTestsFailed"] == 0 and result["escapedDefects"] == 0, result


def case_a_skipped_hidden_test_counts_as_failed(tmp):
    fix = Fix(tmp)
    hidden = HIDDEN_TEST.replace("def test_mul():", "import pytest\n\n\n@pytest.mark.skip\ndef test_mul():")
    write(os.path.join(fix.task_dir, "grading", "tests", "test_calc.py.frozen"), hidden)
    result = graded(fix)
    return result["escapedDefects"] == 1, result


def case_a_test_that_is_not_collected_counts_as_failed(tmp):
    fix = Fix(tmp)
    hidden = HIDDEN_TEST.replace("def test_mul_zero():", "def helper_mul_zero():")
    write(os.path.join(fix.task_dir, "grading", "tests", "test_calc.py.frozen"), hidden)
    result = graded(fix)
    return result["escapedDefects"] == 1, result


# --------------------------------------------------------------------------
# cost and usage

def transcript_home(tmp, main_lines, subagents=None):
    home = os.path.join(tmp, "usage-home")
    proj = os.path.join(home, ".claude", "projects", "-run-repo")
    write(os.path.join(proj, "s1.jsonl"), "".join(json.dumps(r) + "\n" for r in main_lines))
    for name, lines in (subagents or {}).items():
        write(os.path.join(proj, "s1", "subagents", f"agent-{name}.jsonl"),
              "".join(json.dumps(r) + "\n" for r in lines))
    return home


def assistant(mid, out, sidechain=False, model="claude-sonnet-5-5"):
    return {"type": "assistant", "timestamp": "2026-10-19T00:00:00Z", "isSidechain": sidechain,
            "message": {"id": mid, "model": model, "usage": {
                "input_tokens": 1_000_000, "output_tokens": out, "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0}}}


def case_claude_cost_counts_subagent_files_and_each_message_once(tmp):
    home = transcript_home(tmp, [assistant("a", 100), assistant("a", 100),
                                 {"type": "user", "toolUseResult": {"agentId": "x1"}}],
                           {"x1": [assistant("b", 1_000_000, sidechain=True)]})
    tokens, cost, _ = eval_mod.claude_usage(home)
    ok = tokens != UNKNOWN and tokens["input"] == 2_000_000 and cost == round(2 * 2.0 + (100 + 1_000_000) * 10 / 1e6, 6)
    return ok, (tokens, cost)


def case_a_missing_subagent_transcript_makes_cost_unknown(tmp):
    home = transcript_home(tmp, [assistant("a", 100), {"type": "user", "toolUseResult": {"agentId": "ghost"}}])
    tokens, cost, notes = eval_mod.claude_usage(home)
    return cost == UNKNOWN and tokens != UNKNOWN and any("ghost" in n for n in notes), (tokens, cost, notes)


def case_an_unparseable_transcript_makes_usage_unknown(tmp):
    home = transcript_home(tmp, [assistant("a", 100)])
    with open(os.path.join(home, ".claude", "projects", "-run-repo", "s1.jsonl"), "a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    tokens, cost, _ = eval_mod.claude_usage(home)
    return tokens == UNKNOWN and cost == UNKNOWN, (tokens, cost)


def case_an_unpriced_model_makes_cost_unknown(tmp):
    home = transcript_home(tmp, [assistant("a", 100, model="mystery-model-9")])
    _tokens, cost, unpriced = eval_mod.claude_usage(home)
    return cost == UNKNOWN and unpriced == ["mystery-model-9"], (cost, unpriced)


def case_no_transcripts_is_unknown_not_zero(tmp):
    tokens, cost, _ = eval_mod.claude_usage(os.path.join(tmp, "empty-home"))
    return tokens == UNKNOWN and cost == UNKNOWN, (tokens, cost)


def codex_events(tmp, usages, sessions=0):
    repo = os.path.join(tmp, "crepo")
    home = os.path.join(tmp, "chome")
    for n, usage in enumerate(usages):
        write(os.path.join(repo, ".work", "review", f"r{n}", "codex-events.jsonl"),
              json.dumps({"type": "thread.started", "thread_id": f"thread-{n}"}) + "\n"
              + json.dumps({"type": "turn.completed", "usage": usage}) + "\n")
    for n in range(sessions):
        write(os.path.join(home, ".codex", "sessions", f"rollout-2026-thread-{n}.jsonl"), "{}\n")
    return repo, home


USAGE = {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 50, "reasoning_output_tokens": 20}


def case_codex_tokens_sum_the_turn_completed_usage(tmp):
    repo, home = codex_events(tmp, [USAGE, USAGE], sessions=2)
    tokens, cost = eval_mod.codex_usage(repo, home, "unpriced-model")
    return tokens["input"] == 2000 and tokens["output"] == 100 and cost == UNKNOWN, (tokens, cost)


def case_codex_session_without_an_events_file_makes_usage_unknown(tmp):
    repo, home = codex_events(tmp, [USAGE], sessions=2)
    tokens, cost = eval_mod.codex_usage(repo, home, "m")
    return tokens == UNKNOWN and cost == UNKNOWN, (tokens, cost)


def case_no_codex_call_is_zero_cost(tmp):
    repo, home = codex_events(tmp, [], sessions=0)
    tokens, cost = eval_mod.codex_usage(repo, home, "m")
    return tokens["input"] == 0 and cost == 0.0, (tokens, cost)


def case_codex_cost_uses_a_dated_price_row(tmp):
    repo, home = codex_events(tmp, [USAGE], sessions=1)
    eval_mod.CODEX_PRICES["priced-model"] = {"input": 10.0, "cachedInput": 1.0, "output": 40.0}
    try:
        _tokens, cost = eval_mod.codex_usage(repo, home, "priced-model")
    finally:
        del eval_mod.CODEX_PRICES["priced-model"]
    expected = round((600 * 10.0 + 400 * 1.0 + 50 * 40.0) / 1e6, 6)
    return cost == expected, (cost, expected)


def case_crew_rounds_wrong_shape_ledger_is_incomplete_not_an_exception(tmp):
    repo = os.path.join(tmp, "ledger-repo")
    write(os.path.join(repo, ".git", "crew", "review", "a.json"), json.dumps({"rounds": ["x", {"verdict": "CLEAN"}]}))
    write(os.path.join(repo, ".git", "crew", "review", "b.json"), json.dumps({"rounds": 5}))
    cycles, incomplete = eval_mod.crew_rounds(repo)
    return (cycles, incomplete) == (1, 2), (cycles, incomplete)


def case_pinned_codex_model_has_a_price_row_and_a_known_cost(tmp):
    with open(os.path.join(REAL_EVAL_DIR, "arms", "crew.json"), encoding="utf-8") as fh:
        model = json.load(fh)["reviewer"]["model"]
    repo, home = codex_events(tmp, [USAGE], sessions=1)
    _tokens, cost = eval_mod.codex_usage(repo, home, model)
    expected = round((600 * 2.00 + 400 * 0.20 + 50 * 10.00) / 1e6, 6)
    return model in eval_mod.CODEX_PRICES and eval_mod.CODEX_PRICES_AS_OF and cost == expected, (model, cost, expected)


# --------------------------------------------------------------------------
# contamination

def run_with_text(fix, text, proxy_lines=()):
    task = fix.load()
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
    write(os.path.join(run["home"], ".claude", "projects", "-run-repo", "s.jsonl"), json.dumps({"text": text}) + "\n")
    log = os.path.join(run["proxylog"], "proxy.jsonl")
    write(log, "".join(json.dumps(p) + "\n" for p in proxy_lines))
    return eval_mod.contamination(task, run["home"], run["repo"], log, fix.arm, fix.src)


def case_contamination_flags_the_reference_sha(tmp):
    fix = Fix(tmp)
    reasons = run_with_text(fix, "I looked at " + fix.reference)
    return reasons == ["reference sha"], reasons


def case_contamination_flags_the_reference_pr_url(tmp):
    reasons = run_with_text(Fix(tmp), "see https://github.com/x/y/pull/4242")
    return reasons == ["reference PR URL"], reasons


def case_contamination_does_not_flag_readme_text_or_the_repo_path(tmp):
    fix = Fix(tmp)
    readme = slurp(os.path.join(fix.src, "README.md"))
    reasons = run_with_text(fix, readme + " mbadali25/useful-claude-add-ons and pull request numbers like #12")
    return reasons == [], reasons


def case_contamination_flags_hidden_test_content_but_not_a_few_shared_lines(tmp):
    base = os.path.join(tmp, "a")
    os.makedirs(base)
    fix = Fix(base)
    one = run_with_text(fix, LONG1 + "\n" + LONG2)
    three = run_with_text(Fix(os.path.join(tmp, "b")) if os.makedirs(os.path.join(tmp, "b")) is None else None,
                          LONG1 + "\n" + LONG2 + "\n" + LONG3)
    return one == [] and three == ["hidden test content"], (one, three)


def case_contamination_ignores_hidden_lines_the_statement_gives(tmp):
    fix = Fix(tmp)
    write(os.path.join(fix.task_dir, "statement.md"), "Examples:\n" + LONG1 + "\n" + LONG2 + "\n" + LONG3 + "\n")
    reasons = run_with_text(fix, LONG1 + "\n" + LONG2 + "\n" + LONG3)
    return reasons == [], reasons


def case_contamination_flags_a_refused_host_but_not_an_ignored_one(tmp):
    fix = Fix(tmp)
    denied = run_with_text(fix, "x", [{"host": "github.com", "decision": "deny"}])
    ignored = run_with_text(Fix(os.path.join(tmp, "c")) if os.makedirs(os.path.join(tmp, "c")) is None else None,
                            "x", [{"host": "telemetry.example", "decision": "deny"},
                                  {"host": "api.anthropic.com", "decision": "allow"}])
    return denied == ["network host github.com"] and ignored == [], (denied, ignored)


# --------------------------------------------------------------------------
# budget

def row(task="t", bucket="S", arm="crew", cost=1.0, **extra):
    return {"task": task, "bucket": bucket, "arm": arm, "attempt": 1, "costUsd": cost, "runStatus": "scored", **extra}


def case_first_pilot_run_uses_the_first_run_estimate(tmp):
    spent, projection = eval_mod.budget_check([], "S", "crew", 150.0, 25.0)
    message = refused(eval_mod.budget_check, [], "S", "crew", 20.0, 25.0)
    ok = (spent, projection) == (0.0, 25.0) and bool(message and "would pass" in message)
    return ok, (spent, projection, message)


def case_budget_projects_the_highest_observed_cost_for_the_bucket_and_arm(tmp):
    rows = [row(cost=10.0), row(cost=30.0), row(bucket="M", cost=90.0), row(arm="baseline", cost=60.0)]
    spent, projection = eval_mod.budget_check(rows, "S", "crew", 220.0, 25.0)
    message = refused(eval_mod.budget_check, rows, "S", "crew", 219.0, 25.0)
    return projection == 30.0 and spent == 190.0 and message is not None, (spent, projection, message)


def case_budget_falls_back_to_the_arms_pilot_cost_in_a_new_bucket(tmp):
    _spent, projection = eval_mod.budget_check([row(cost=12.0)], "M", "crew", 150.0, 25.0)
    return projection == 12.0, projection


def case_an_unknown_cost_run_stops_the_batch(tmp):
    rows = [row(cost=1.0), row(cost=UNKNOWN, ownCostUsd=UNKNOWN)]
    message = refused(eval_mod.budget_check, rows, "S", "crew", 150.0, 25.0)
    return bool(message and "UNKNOWN" in message), message


def case_budget_counts_each_attempt_once_not_the_carried_cost(tmp):
    first = row(cost=4.0, ownCostUsd=4.0)
    second = row(cost=7.0, ownCostUsd=3.0)
    spent, _ = eval_mod.budget_check([first, second], "S", "crew", 150.0, 25.0)
    return spent == 7.0, spent


def case_results_are_appended_as_full_json_lines(tmp):
    path = os.path.join(tmp, "r.jsonl")
    eval_mod.append_result(path, {"a": 1})
    eval_mod.append_result(path, {"b": 2})
    lines = slurp(path).splitlines()
    return [json.loads(x) for x in lines] == [{"a": 1}, {"b": 2}], lines


# --------------------------------------------------------------------------
# end to end through the stub docker

def run_arm(fix, mode, arm=None, **env):
    fix.env.update({"STUB_MODE": mode, **env})
    ctx = fix.ctx()
    with patched_env(fix.env):
        task = fix.load()
        return eval_mod.run_once(ctx, task, arm or fix.arm, 1), ctx


def case_a_stub_baseline_run_is_scored_and_costed(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "ok", STUB_RESULT="No findings.")
    ok = (result["runStatus"] == "scored" and result["escapedDefects"] == 0 and result["reviewCycles"] == 1
          and result["claudeCostUsd"] != UNKNOWN and result["costUsd"] == result["claudeCostUsd"]
          and result["cliTotalCostUsd"] == 1.0 and result["tokens"] != UNKNOWN)
    return ok, result


def case_a_baseline_run_fixes_findings_then_stops_at_three_cycles(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "ok", STUB_RESULT="FINDING: x")
    return result["reviewCycles"] == 3, result["reviewCycles"]


def case_an_unparseable_review_counts_as_incomplete_not_a_cycle(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "ok", STUB_RESULT="hmm")
    return result["reviewCycles"] == 0 and result["reviewAttemptsIncomplete"] == 2, result


def case_a_stub_run_through_docker_has_no_network_and_reaches_only_the_proxy_socket(tmp):
    fix = Fix(tmp)
    run_arm(fix, "ok", STUB_RESULT="No findings.")
    calls = [json.loads(x) for x in slurp(fix.docker_log).splitlines()]
    runs = [c for c in calls if c[:1] == ["run"]]
    arm_runs = [c for c in runs if any(a.endswith(":/run/proxy") for a in c)]
    ok = (bool(arm_runs) and len(arm_runs) < len(runs)
          and not any(c[:1] == ["network"] for c in calls)
          and all(c[c.index("--network") + 1] == "none" for c in runs)
          and not any(c[:2] == ["run", "-d"] for c in calls))
    return ok, [c[:2] for c in calls]


def case_a_contaminated_run_is_marked_and_still_costed(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "mentions-reference", STUB_RESULT="No findings.")
    return result["runStatus"] == "contaminated" and "reference sha" in result["contamination"], result["runStatus"]


def case_a_missing_subagent_transcript_makes_the_run_cost_unknown(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "subagent-missing", STUB_RESULT="No findings.")
    return result["costUsd"] == UNKNOWN and result["runStatus"] == "scored", result


def case_a_paid_unscorable_attempt_is_carried_into_its_rerun(tmp):
    fix = Fix(tmp)
    fix.env.update({"STUB_MODE": "fail-first", "STUB_RESULT": "No findings."})
    ctx = fix.ctx()
    with patched_env(fix.env):
        final = eval_mod.run_chain(ctx, fix.load(), fix.arm)
    rows = eval_mod.read_results(fix.results)
    ok = (len(rows) == 2 and rows[0]["runStatus"] == "unscorable" and final["runStatus"] == "scored"
          and rows[0]["unscoredSpendUsd"] == rows[0]["ownCostUsd"]
          and final["costUsd"] == round(rows[0]["ownCostUsd"] + final["ownCostUsd"], 6))
    return ok, rows


def case_an_exhausted_paid_failure_keeps_its_spend(tmp):
    fix = Fix(tmp)
    fix.env.update({"STUB_MODE": "always-fail"})
    ctx = fix.ctx()
    with patched_env(fix.env):
        final = eval_mod.run_chain(ctx, fix.load(), fix.arm)
    rows = eval_mod.read_results(fix.results)
    spend = final.get("unscoredSpendUsd")
    ok = (len(rows) == 2 and final["runStatus"] == "unscorable"
          and isinstance(spend, float) and spend > 0
          and final["costUsd"] == final["unscoredSpendUsd"])
    return ok, rows


def case_cli_cost_counts_each_session_once_not_cumulatively(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "ok", STUB_RESULT="FINDING: x")
    return result["cliTotalCostUsd"] == 3.5, result["cliTotalCostUsd"]


def case_every_cli_json_is_kept_beside_the_run(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "ok", STUB_RESULT="No findings.")
    kept = sorted(os.listdir(os.path.join(result["runDir"], "cli")))
    return len(kept) == 2 and kept[0].endswith(".json"), kept


def case_the_argv_carries_git_identity_and_the_isolation_options(tmp):
    run = {"repo": "/r/repo", "home": "/r/home", "proxylog": "/r/log", "dir": "/r", "proxysock": "/r/sock"}
    argv = eval_mod.arm_docker_argv("/usr/bin/docker", run, "n", ("1000", "1000"), ["x"])
    joined = " ".join(argv)
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    ok = ("GIT_AUTHOR_NAME=" in joined and "GIT_COMMITTER_EMAIL=" in joined and "--user 1000:1000" in joined
          and "--cap-drop ALL" in joined and "no-new-privileges" in joined and "--privileged" not in joined
          and "seccomp=unconfined" not in joined and "apparmor=unconfined" not in joined
          and "--cap-add" not in joined and "--network none" in joined
          and mounts == ["/r/repo:/run/repo", "/r/home:/run/home", "/r/sock:/run/proxy"])
    return ok, joined


def case_the_codex_shim_rewrites_only_the_read_only_sandbox(tmp):
    stub = os.path.join(tmp, "realcodex")
    with open(stub, "w", newline="\n", encoding="utf-8") as fh:
        fh.write('#!/bin/sh\nfor a; do printf "%s\\n" "$a"; done\n')
    os.chmod(stub, 0o755)
    shim = os.path.join(REPO, "evals", "crew-outcome", "container", "codex-shim.sh")
    env = dict(os.environ, CODEX_REAL=stub)
    out = subprocess.run(["/bin/sh", shim, "exec", "--json", "--sandbox", "read-only", "-m", "a b", "-s", "read-only",
                          "--sandbox=read-only", "--sandbox", "workspace-write", "read-only"],
                         capture_output=True, text=True, env=env, check=False)
    want = ["exec", "--json", "--sandbox", "danger-full-access", "-m", "a b", "-s", "danger-full-access",
            "--sandbox=danger-full-access", "--sandbox", "workspace-write", "read-only"]
    docker = read_text(os.path.join(REPO, "evals", "crew-outcome", "container", "Dockerfile"))
    wired = "codex-shim.sh /opt/eval-shim/codex" in docker and "PATH=/opt/eval-shim:" in docker
    return out.stdout.splitlines() == want and wired, (out.stdout, out.stderr, wired)


def case_the_shim_and_canary_are_executable_in_git_and_the_image(tmp):
    container = os.path.join(REAL_EVAL_DIR, "container")
    listing = subprocess.run(["git", "ls-files", "-s", "--", "evals/crew-outcome/container"], cwd=REPO,
                             capture_output=True, text=True, check=False).stdout.splitlines()
    modes = {line.split("\t")[1].rsplit("/", 1)[1]: line.split()[0] for line in listing}
    docker = read_text(os.path.join(container, "Dockerfile"))
    ok = (modes.get("codex-shim.sh") == "100755" and modes.get("canary.sh") == "100755"
          and "chmod 0755 /opt/eval-shim/codex" in docker)
    return ok, (modes, "chmod" in docker)


def case_the_canary_runs_under_the_scored_isolation_settings(tmp):
    canary = read_text(os.path.join(REAL_EVAL_DIR, "container", "canary.sh"))
    ok = ("--cap-drop ALL" in canary and "no-new-privileges" in canary and "--user 1000:1000" in canary
          and "seccomp" not in canary and "apparmor" not in canary and "--privileged" not in canary
          and "--cap-add" not in canary)
    return ok, [w for w in ("seccomp", "apparmor", "--privileged", "--cap-add") if w in canary]


def case_load_refuses_a_malformed_task_with_a_refusal_not_a_traceback(tmp):
    results = []
    for key, value in (("defects", {"d": [[1]]}), ("gradingFiles", None), ("regressionInventory", [3]),
                       ("testCommand", "pytest"), ("referenceLines", "3"), ("base", None)):
        fix = Fix(os.path.join(tmp, key))
        fix.task[key] = value
        write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
        try:
            results.append((key, refused(fix.load) is not None))
        except Exception as exc:  # noqa: BLE001 - the case reports a traceback as the failure it is
            results.append((key, f"raised {type(exc).__name__}"))
    return all(flag is True for _, flag in results), results


def case_a_non_object_results_line_is_refused_not_dropped(tmp):
    path = os.path.join(tmp, "results.jsonl")
    write(path, json.dumps(row()) + "\n[]\n")
    message = refused(eval_mod.read_results, path)
    good = os.path.join(tmp, "good.jsonl")
    write(good, json.dumps(row()) + "\n\n" + json.dumps(row()) + "\n")
    return bool(message and "not a JSON object" in message) and len(eval_mod.read_results(good)) == 2, message


def case_an_unreadable_proxy_log_is_a_contamination_reason(tmp):
    fix = Fix(tmp)
    task = fix.load()
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
    missing = eval_mod.contamination(task, run["home"], run["repo"], os.path.join(tmp, "nope.jsonl"), fix.arm, fix.src)
    bad = os.path.join(tmp, "bad.jsonl")
    write(bad, '{"host": "a", "decision": "allow"}\nnot json\n')
    malformed = eval_mod.contamination(task, run["home"], run["repo"], bad, fix.arm, fix.src)
    shape = os.path.join(tmp, "shape.jsonl")
    write(shape, "[]\n")
    wrong_shape = eval_mod.contamination(task, run["home"], run["repo"], shape, fix.arm, fix.src)
    ok = (missing == ["network audit unreadable"] and malformed == ["network audit unreadable"]
          and wrong_shape == ["network audit unreadable"])
    return ok, (missing, malformed, wrong_shape)


def case_an_empty_proxy_log_is_a_clean_audit(tmp):
    reasons = run_with_text(Fix(tmp), "x", [])
    return reasons == [], reasons


def case_a_rerun_after_an_unscorable_attempt_is_budget_checked_first(tmp):
    fix = Fix(tmp)
    fix.env.update({"STUB_MODE": "always-fail"})
    ctx = fix.ctx()

    def over_budget():
        raise eval_mod.EvalError("budget: spent 9.00 + projected 1.00 would pass --max-cost-usd 5.00")

    ctx["before_rerun"] = over_budget
    with patched_env(fix.env):
        message = refused(eval_mod.run_chain, ctx, fix.load(), fix.arm)
    rows = eval_mod.read_results(fix.results)
    ok = (bool(message and "budget" in message) and len(rows) == 1 and rows[0]["runStatus"] == "unscorable"
          and eval_mod.known(rows[0].get("unscoredSpendUsd")))
    return ok, (message, rows)


def case_a_rerun_within_budget_still_happens(tmp):
    fix = Fix(tmp)
    fix.env.update({"STUB_MODE": "fail-first", "STUB_RESULT": "No findings."})
    ctx = fix.ctx()
    calls = []
    ctx["before_rerun"] = lambda: calls.append(1)
    with patched_env(fix.env):
        final = eval_mod.run_chain(ctx, fix.load(), fix.arm)
    return calls == [1] and final["runStatus"] == "scored", (calls, final["runStatus"])


def case_codex_turn_without_usage_fields_makes_usage_unknown(tmp):
    repo, home = codex_events(tmp, [{}], sessions=1)
    empty = eval_mod.codex_usage(repo, home, "m")
    partial_repo, partial_home = codex_events(os.path.join(tmp, "p"), [{"input_tokens": 5}], sessions=1)
    partial = eval_mod.codex_usage(partial_repo, partial_home, "m")
    ok = empty == (UNKNOWN, UNKNOWN) and partial == (UNKNOWN, UNKNOWN)
    return ok, (empty, partial)


def case_codex_session_with_no_completed_turn_makes_usage_unknown(tmp):
    repo, home = codex_events(tmp, [], sessions=1)
    write(os.path.join(repo, "codex-events.jsonl"), json.dumps({"type": "thread.started"}) + "\n")
    return eval_mod.codex_usage(repo, home, "m") == (UNKNOWN, UNKNOWN), eval_mod.codex_usage(repo, home, "m")


def case_a_grading_run_that_crashes_after_printing_passed_lines_is_missing(tmp):
    def task_for(code):
        script = ("import sys; print('=== short test summary info ==='); print('PASSED tests/x.py::a'); "
                  f"print('1 passed in 0.1s'); sys.exit({code})")
        return {"testCommand": ["python3", "-c", script]}

    got = {code: eval_mod.run_tests(task_for(code), tmp, ["tests/x.py::a"])["tests/x.py::a"]
           for code in (0, 1, 2, 3, 5)}
    ok = got == {0: "PASSED", 1: "PASSED", 2: "MISSING", 3: "MISSING", 5: "MISSING"}
    return ok, got


def case_a_qq_run_with_no_counts_line_still_reads_its_summary(tmp):
    script = "print('=== short test summary info ==='); print('PASSED tests/x.py::a'); print('FAILED tests/x.py::b')"
    status = eval_mod.run_tests({"testCommand": ["python3", "-c", script]}, tmp, ["tests/x.py::a", "tests/x.py::b"])
    return status == {"tests/x.py::a": "PASSED", "tests/x.py::b": "FAILED"}, status


def case_a_printed_passed_line_cannot_override_a_real_failure(tmp):
    script = ("import sys; print('PASSED tests/x.py::a'); print('=== short test summary info ==='); "
              "print('FAILED tests/x.py::a - assert 0'); print('1 failed in 0.1s'); "
              "print('PASSED tests/x.py::b'); sys.exit(1)")
    status = eval_mod.run_tests({"testCommand": ["python3", "-c", script]}, tmp, ["tests/x.py::a", "tests/x.py::b"])
    return status == {"tests/x.py::a": "FAILED", "tests/x.py::b": "MISSING"}, status


def case_a_grading_run_that_hangs_after_its_summary_is_missing(tmp):
    script = ("import sys, time; print('=== short test summary info ==='); print('PASSED tests/x.py::a'); "
              "print('1 passed in 0.1s'); sys.stdout.flush(); time.sleep(30)")
    saved = eval_mod.TEST_TIMEOUT_SECONDS
    eval_mod.TEST_TIMEOUT_SECONDS = 1
    try:
        message = raises_infra(eval_mod.run_tests, {"testCommand": ["python3", "-c", script]}, tmp, ["tests/x.py::a"])
    finally:
        eval_mod.TEST_TIMEOUT_SECONDS = saved
    return bool(message and "timed out" in message), message


def case_an_arm_edited_pytest_config_is_restored_for_grading(tmp):
    def tamper(repo):
        write(os.path.join(repo, "pytest.ini"), "[pytest]\naddopts = -k nothing_matches\n")
        write(os.path.join(repo, "tests", "conftest.py"), "raise RuntimeError('arm conftest')\n")
        write(os.path.join(repo, "sitecustomize.py"), "raise SystemExit(7)\n")

    result = graded(Fix(tmp), mutate=tamper)
    return result["escapedDefects"] == 0 and result["regressionTestsFailed"] == 0, result


def case_a_claude_cli_session_without_a_transcript_makes_cost_unknown(tmp):
    home = transcript_home(tmp, [assistant("m1", 1000)])
    complete = eval_mod.claude_usage(home, ["s1"])
    missing = eval_mod.claude_usage(home, ["s1", "s2"])
    return complete[1] != UNKNOWN and missing[1] == UNKNOWN, (complete[1], missing[1])


def case_a_codex_session_no_events_file_names_makes_usage_unknown(tmp):
    repo, home = codex_events(tmp, [USAGE], sessions=1)
    write(os.path.join(repo, ".work", "review", "other", "codex-events.jsonl"),
          json.dumps({"type": "thread.started", "thread_id": "thread-other"}) + "\n")
    write(os.path.join(home, ".codex", "sessions", "rollout-2026-thread-unnamed.jsonl"), "{}\n")
    return eval_mod.codex_usage(repo, home, "m") == (UNKNOWN, UNKNOWN), eval_mod.codex_usage(repo, home, "m")


def case_a_failed_docker_kill_after_a_timeout_stops_the_run(tmp):
    fix = Fix(tmp)
    docker = os.path.join(tmp, "stuck-docker")
    write(docker, "#!/bin/sh\ncase \"$1\" in run) sleep 30;; kill) exit 1;; inspect) echo true;; rm) exit 0;; "
          "esac\n", EXEC)
    run = {"repo": "/r/repo", "home": "/r/home", "proxylog": "/r/log", "dir": "/r", "proxysock": "/r/sock"}
    with patched_env(fix.env):
        message = refused(eval_mod.invoke, docker, run, "n", ["x"], 1)
    return bool(message and "could not be stopped" in message), message


def case_a_canary_goes_stale_when_the_proxy_allowlist_changes(tmp):
    fix = Fix(tmp)
    eval_dir = os.path.join(tmp, "evaldir")
    shutil.copytree(os.path.join(REAL_EVAL_DIR, "container"), os.path.join(eval_dir, "container"))
    canary = os.path.join(os.path.dirname(fix.results), "canary.txt")
    fingerprint = eval_mod.canary_fingerprint(eval_dir)
    write(canary, f"canary: t image=sha256:x network=none fingerprint={fingerprint}\nPASS x\ncanary: PASS\n")
    fresh = eval_mod.canary_ok(fix.results, None, eval_dir)
    with open(os.path.join(eval_dir, "container", "proxy-allowlist.txt"), "a", encoding="utf-8") as fh:
        fh.write("github.com\n")
    stale = eval_mod.canary_ok(fix.results, None, eval_dir)
    return (fresh, stale) == (True, False), (fresh, stale)


def case_the_canary_script_demands_the_three_host_paths_and_records_the_fingerprint(tmp):
    canary = read_text(os.path.join(REAL_EVAL_DIR, "container", "canary.sh"))
    return '"$#" -lt 4' in canary and "fingerprint=$FINGERPRINT" in canary, '"$#" -lt 4' in canary


def case_the_budget_flags_refuse_nan_infinity_and_non_positive_amounts(tmp):
    bad = []
    for text in ("nan", "inf", "-1", "0", "abc"):
        try:
            eval_mod.positive_amount(text)
        except argparse.ArgumentTypeError:
            continue
        bad.append(text)
    return not bad and eval_mod.positive_amount("5") == 5.0, bad


def case_a_second_run_on_one_results_file_is_refused(tmp):
    path = os.path.join(tmp, "results.jsonl")
    first = eval_mod.lock_results(path)
    message = refused(eval_mod.lock_results, path)
    first.close()
    again = eval_mod.lock_results(path)
    again.close()
    return bool(message and "another run" in message), message


def case_the_t_0107_task_names_its_reference_pr(tmp):
    task = eval_mod.load_task(os.path.join(REAL_EVAL_DIR, "tasks", "t-0107-gizmoduck-routine-cli"))
    return task.get("referencePr") == 273, task.get("referencePr")


def case_a_compact_json_findings_array_parses_as_findings(tmp):
    arm = eval_mod.check_method(REAL_EVAL_DIR)["baseline"]
    compact = '[{"file":"x","line":1,"summary":"bug"}]'
    pretty = '[\n  {\n    "summary": "bug"\n  }\n]'
    got = [eval_mod.review_verdict(arm, compact), eval_mod.review_verdict(arm, pretty),
           eval_mod.review_verdict(arm, "[]"), eval_mod.review_verdict(arm, "no idea")]
    return got == ["findings", "findings", "clean", "unparseable"], got


def case_grading_runs_in_a_no_network_container_with_only_the_copy_mounted(tmp):
    argv = eval_mod.grade_docker_argv("/usr/bin/docker", "n", ("1000", "1000"), "/r/copy", ["python3", "-m", "pytest"])
    joined = " ".join(argv)
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    ok = ("--network none" in joined and "--cap-drop ALL" in joined and "no-new-privileges" in joined
          and "--pids-limit" in joined and "--memory" in joined and "--user 1000:1000" in joined
          and "--privileged" not in joined and "--cap-add" not in joined and "seccomp" not in joined
          and mounts == ["/r/copy:/run/repo"] and argv[-3:] == ["python3", "-m", "pytest"])
    return ok, joined


def case_grading_goes_through_docker_and_not_the_host_python(tmp):
    fix = Fix(tmp)
    with patched_env(fix.env):
        graded(fix)
    log = [json.loads(line) for line in slurp(fix.docker_log).splitlines()]
    runs = [a for a in log if a[:1] == ["run"]]
    return len(runs) == 2 and all("none" == a[a.index("--network") + 1] for a in runs), runs


def case_the_arm_and_grading_share_the_isolation_options(tmp):
    run = {"repo": "/r/repo", "home": "/r/home", "proxylog": "/r/log", "dir": "/r", "proxysock": "/r/sock"}
    arm = eval_mod.arm_docker_argv("/usr/bin/docker", run, "n", ("1000", "1000"), ["x"])
    grade = eval_mod.grade_docker_argv("/usr/bin/docker", "n", ("1000", "1000"), "/r/c", ["x"])
    joined_arm, joined_grade = " ".join(arm), " ".join(grade)
    shared = " ".join(eval_mod.ISOLATION_OPTIONS)
    return shared in joined_arm and shared in joined_grade, (shared, joined_arm)


def case_overlay_does_not_write_through_a_symlink_the_arm_planted(tmp):
    fix = Fix(tmp)
    outside = os.path.join(tmp, "outside")
    write(os.path.join(outside, "victim.txt"), "OWNER FILE\n")

    def plant(repo):
        os.remove(os.path.join(repo, "tests", "test_calc.py"))
        os.symlink(os.path.join(outside, "victim.txt"), os.path.join(repo, "tests", "test_calc.py"))
        os.symlink(outside, os.path.join(repo, "linkdir"))

    graded(fix, mutate=plant)
    return slurp(os.path.join(outside, "victim.txt")) == "OWNER FILE\n", slurp(os.path.join(outside, "victim.txt"))


def case_overlay_replaces_a_symlinked_directory_on_the_path(tmp):
    fix = Fix(tmp)
    outside = os.path.join(tmp, "outside-dir")
    os.makedirs(outside)
    repo = os.path.join(tmp, "copy")
    os.makedirs(repo)
    os.symlink(outside, os.path.join(repo, "tests"))
    eval_mod.place(repo, "tests/test_calc.py", os.path.join(fix.task_dir, "grading", "conftest.py.frozen"))
    ok = os.listdir(outside) == [] and os.path.isfile(os.path.join(repo, "tests", "test_calc.py")) \
        and not os.path.islink(os.path.join(repo, "tests"))
    return ok, os.listdir(outside)


def case_load_refuses_a_grading_path_that_leaves_the_repository(tmp):
    got = []
    for key, value in (("gradingFiles", ["../evil.py"]), ("gradingFiles", ["/etc/passwd"]),
                       ("regressionInventory", ["../x.py::t"])):
        fix = Fix(os.path.join(tmp, f"{key}{len(got)}"))
        fix.task[key] = value
        write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
        got.append(refused(fix.load))
    return all(got) and "inside the repository" in got[0], got


def case_a_fifo_where_a_transcript_or_events_file_belongs_is_unknown_not_a_hang(tmp):
    repo, home = codex_events(tmp, [], sessions=1)
    os.makedirs(repo, exist_ok=True)
    os.mkfifo(os.path.join(repo, "codex-events.jsonl"))
    codex = eval_mod.codex_usage(repo, home, "m")
    fix = Fix(os.path.join(tmp, "c"))
    task = fix.load()
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
    os.mkfifo(os.path.join(run["repo"], "codex-events.jsonl"))
    log = os.path.join(run["proxylog"], "proxy.jsonl")
    write(log, "")
    reasons = eval_mod.contamination(task, run["home"], run["repo"], log, fix.arm, fix.src)
    return codex == (UNKNOWN, UNKNOWN) and reasons == ["unreadable arm file"], (codex, reasons)


def case_a_canary_for_another_image_does_not_open_the_gate(tmp):
    fix = Fix(tmp)
    canary = os.path.join(os.path.dirname(fix.results), "canary.txt")
    docker = os.path.join(fix.bin, "docker")
    write(os.path.join(fix.bin, "docker"), "#!/bin/sh\necho sha256:current\n", EXEC)
    write(canary, "canary: t image=sha256:old network=n\nPASS x\ncanary: PASS\n")
    stale = eval_mod.canary_ok(fix.results, docker)
    write(canary, "canary: t image=sha256:current network=n\nPASS x\ncanary: PASS\n")
    current = eval_mod.canary_ok(fix.results, docker)
    return (stale, current) == (False, True), (stale, current)


def case_the_canary_mirrors_the_arm_isolation_options_and_probes_the_gateway(tmp):
    canary = read_text(os.path.join(REAL_EVAL_DIR, "container", "canary.sh"))
    shared = " ".join(eval_mod.ISOLATION_OPTIONS)
    ok = (shared in canary and "--network none" in canary and "/sys/class/net" in canary
          and "network create" not in canary and "eval-run" in canary)
    return ok, (shared in canary, "--network none" in canary, "/sys/class/net" in canary)


def case_a_malformed_or_non_finite_results_row_spends_unknown_not_zero(tmp):
    got = [eval_mod.spend_of(r) for r in ({}, {"ownCostUsd": float("nan")}, {"costUsd": None}, {"costUsd": -1},
                                           {"ownCostUsd": "3"}, {"ownCostUsd": float("inf")})]
    good = [eval_mod.spend_of({"costUsd": 2}), eval_mod.spend_of({"ownCostUsd": 1.5, "costUsd": 9})]
    return got == [UNKNOWN] * 6 and good == [2.0, 1.5], (got, good)


def case_a_cli_error_result_is_unscorable_whatever_its_message(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "error-json")
    failure = result["failure"]
    return result["runStatus"] == "unscorable" and "CLI reported an error" in (failure or ""), failure


def case_a_completed_codex_review_with_no_usage_files_is_unknown(tmp):
    repo = os.path.join(tmp, "crepo")
    home = os.path.join(tmp, "chome")
    ledger = {"rounds": [{"provider": "codex", "refunded": False, "verdict": "CLEAN"}]}
    write(os.path.join(repo, ".git", "crew", "review", "T-1.json"), json.dumps(ledger))
    bare = eval_mod.codex_usage(repo, home, "m")
    refunded = {"rounds": [{"provider": "codex", "refunded": True}, {"provider": "kimi", "refunded": False}]}
    write(os.path.join(repo, ".git", "crew", "review", "T-1.json"), json.dumps(refunded))
    none_counted = eval_mod.codex_usage(repo, home, "m")
    write(os.path.join(repo, ".git", "crew", "review", "T-1.json"), "not json")
    unreadable = eval_mod.codex_usage(repo, home, "m")
    ok = bare == (UNKNOWN, UNKNOWN) and unreadable == (UNKNOWN, UNKNOWN) and none_counted[1] == 0.0
    return ok, (bare, none_counted, unreadable)


def case_the_canary_fails_when_its_proxy_log_does_not_parse(tmp):
    canary = read_text(os.path.join(REAL_EVAL_DIR, "container", "canary.sh"))
    parses = "does not parse" in canary
    return parses and "rc=1" in canary and "except OSError" not in canary, parses


def case_an_indeterminate_container_state_after_a_failed_kill_stops_the_run(tmp):
    fix = Fix(tmp)
    docker = os.path.join(tmp, "blind-docker")
    write(docker, "#!/bin/sh\ncase \"$1\" in run) sleep 30;; kill) exit 1;; inspect) exit 1;; rm) exit 1;; "
          "esac\n", EXEC)
    gone = os.path.join(tmp, "gone-docker")
    write(gone, "#!/bin/sh\ncase \"$1\" in run) sleep 30;; kill) exit 1;; "
          "inspect) echo 'Error: No such object' >&2; exit 1;; rm) exit 0;; esac\n", EXEC)
    run = {"repo": "/r/repo", "home": "/r/home", "proxylog": "/r/log", "dir": "/r", "proxysock": "/r/sock"}
    with patched_env(fix.env):
        blind = refused(eval_mod.invoke, docker, run, "n", ["x"], 1)
        code, _text, timed = eval_mod.invoke(gone, run, "n", ["x"], 1)
    return bool(blind and "could not be stopped" in blind) and (code, timed) == (124, True), (blind, code, timed)


def case_proxy_traffic_to_openai_with_no_codex_files_makes_usage_unknown(tmp):
    repo = os.path.join(tmp, "crepo")
    os.makedirs(repo)
    home = os.path.join(tmp, "chome")
    log = os.path.join(tmp, "proxy.jsonl")
    write(log, json.dumps({"host": "chatgpt.com", "decision": "allow"}) + "\n")
    seen = eval_mod.codex_usage(repo, home, "m", log)
    write(log, json.dumps({"host": "api.anthropic.com", "decision": "allow"}) + "\n"
          + json.dumps({"host": "chatgpt.com", "decision": "deny"}) + "\n")
    none_seen = eval_mod.codex_usage(repo, home, "m", log)
    write(log, "not json\n")
    unreadable = eval_mod.codex_usage(repo, home, "m", log)
    ok = seen == (UNKNOWN, UNKNOWN) and unreadable == (UNKNOWN, UNKNOWN) and none_seen[1] == 0.0
    return ok, (seen, none_seen, unreadable)


def case_the_canary_script_refuses_host_paths_that_do_not_exist(tmp):
    script = os.path.join(REAL_EVAL_DIR, "container", "canary.sh")
    out = subprocess.run(["/bin/bash", script, os.path.join(tmp, "out.txt"), "/nope/a", "/nope/b", "/nope/c"],
                         capture_output=True, text=True, check=False, env=dict(os.environ, DOCKER="/bin/true"))
    return out.returncode == 2 and "does not exist on the host" in out.stderr, (out.returncode, out.stderr[:200])


def case_a_file_where_the_base_has_a_directory_is_a_refusal_not_a_traceback(tmp):
    repo = os.path.join(tmp, "copy")
    write(os.path.join(repo, "tests"), "i am a file\n")
    src = os.path.join(tmp, "src.py")
    write(src, "x\n")
    message = refused(eval_mod.place, repo, "tests/conftest.py", src)
    return bool(message and "needs a directory" in message), message


def case_autopilot_stopped_only_on_a_readable_stop_0_keeps_going(tmp):
    def shell(text, code=0):
        return lambda command: (code, text)
    got = [eval_mod.autopilot_stopped(shell("phase=spec stop=0 command=/crew:spec"), "T-1"),
           eval_mod.autopilot_stopped(shell("phase=review stop=1 decision=accept"), "T-1"),
           eval_mod.autopilot_stopped(shell("garbage"), "T-1"),
           eval_mod.autopilot_stopped(shell("", 1), "T-1"),
           eval_mod.autopilot_stopped(shell("stop=0", 1), "T-1")]
    return got == [False, True, None, None, None], got


def case_a_crew_arm_assigns_a_ticket_then_resumes_while_autopilot_says_stop_0(tmp):
    fix = Fix(tmp)
    arm = eval_mod.load_arm(os.path.join(REAL_EVAL_DIR, "arms", "crew.json"))
    result, _ = run_arm(fix, "ok", arm=arm, STUB_RESULT="working")
    index = slurp(os.path.join(result["runDir"], "repo", ".work", "INDEX.md"))
    calls = int(slurp(fix.env["STUB_STATE"]))
    ok = ("T-0001" in index and calls == 1 + arm["cli"]["maxResumes"]
          and result["endedBy"] == "resume-cap" and result["failure"] is None
          and result["runStatus"] == "scored" and result["escapedDefects"] == 0)
    return ok, (index, calls, result["failure"], result["runStatus"], result.get("endedBy"))


def case_a_crew_arm_whose_assign_fails_is_unscorable(tmp):
    fix = Fix(tmp)
    arm = eval_mod.load_arm(os.path.join(REAL_EVAL_DIR, "arms", "crew.json"))
    arm["assignment"] = dict(arm["assignment"], template="no title line here\n")
    result, _ = run_arm(fix, "ok", arm=arm)
    return result["runStatus"] == "unscorable" and "assign failed" in (result["failure"] or ""), result["failure"]


def case_run_refuses_without_a_passing_canary(tmp):
    fix = Fix(tmp)
    ok_before = eval_mod.canary_ok(fix.results)
    write(os.path.join(os.path.dirname(fix.results), "canary.txt"), "PASS something\ncanary: FAIL\n")
    failed = eval_mod.canary_ok(fix.results)
    write(os.path.join(os.path.dirname(fix.results), "canary.txt"), "PASS something\ncanary: PASS\n")
    passed = eval_mod.canary_ok(fix.results)
    return (ok_before, failed, passed) == (False, False, True), (ok_before, failed, passed)


def case_docker_missing_is_a_refusal_not_a_bare_name(tmp):
    with patched_env({"PATH": os.path.join(tmp, "nowhere"), "HOME": tmp}):
        message = refused(eval_mod.which, "docker")
    return bool(message and "not found" in message), message


# --------------------------------------------------------------------------
# report and verdict

def runs(task, arm, bucket, defects, costs, **extra):
    return [{"task": task, "bucket": bucket, "arm": arm, "attempt": i + 1, "runStatus": "scored",
             "escapedDefects": defects, "costUsd": cost, "regressionTestsFailed": 0, "defectsTotal": 4, **extra}
            for i, cost in enumerate(costs)]


def two_tasks(bucket="S", crew_defects=0, base_defects=2, crew_cost=10.0, base_cost=4.0):
    rows = []
    for task in ("a", "b"):
        rows += runs(task, "crew", bucket, crew_defects, [crew_cost, crew_cost])
        rows += runs(task, "baseline", bucket, base_defects, [base_cost, base_cost])
    return rows


def case_verdict_states_the_break_even_value(tmp):
    verdict = eval_mod.bucket_verdict(two_tasks(), "S")
    return verdict["breakEvenUsd"] == 3.0 and "values one escaped defect above 3.00 USD" in verdict["lines"][0], verdict


def case_verdict_says_no_fewer_defects_when_the_difference_is_not_negative(tmp):
    verdict = eval_mod.bucket_verdict(two_tasks(crew_defects=2, base_defects=2), "S")
    return verdict["verdict"] == "crew leaves no fewer escaped defects", verdict


def case_verdict_says_free_when_crew_is_cheaper_and_avoids_defects(tmp):
    verdict = eval_mod.bucket_verdict(two_tasks(crew_cost=3.0, base_cost=4.0), "S")
    return verdict["verdict"] == "crew pays for itself", verdict


def case_verdict_empty_bucket_is_could_not_tell(tmp):
    text = eval_mod.report_text(two_tasks("S"))
    return "## Bucket M\ncould not tell: no tasks in this bucket" in text, text


def case_verdict_one_task_is_could_not_tell(tmp):
    rows = runs("a", "crew", "S", 0, [5, 5]) + runs("a", "baseline", "S", 2, [4, 4])
    verdict = eval_mod.bucket_verdict(rows, "S")
    return verdict["verdict"] == "could not tell" and "1 task(s)" in verdict["lines"][0], verdict


def case_verdict_drops_a_task_with_fewer_than_two_known_runs_in_an_arm(tmp):
    rows = two_tasks()
    rows = [r for r in rows if not (r["task"] == "b" and r["arm"] == "baseline" and r["attempt"] == 2)]
    verdict = eval_mod.bucket_verdict(rows, "S")
    return verdict["dropped"] == ["b"] and verdict["verdict"] == "could not tell", verdict


def case_verdict_unknown_cost_is_could_not_tell(tmp):
    rows = two_tasks()
    rows[0]["costUsd"] = UNKNOWN
    verdict = eval_mod.bucket_verdict(rows, "S")
    return verdict["verdict"] == "could not tell" and "UNKNOWN" in verdict["lines"][0], verdict


def case_verdict_exhausted_spend_counts_in_the_paired_cost_difference(tmp):
    rows = two_tasks()
    rows.append({"task": "a", "bucket": "S", "arm": "crew", "attempt": 2, "runStatus": "unscorable",
                 "costUsd": 0.0, "unscoredSpendUsd": 6.0})
    verdict = eval_mod.bucket_verdict(rows, "S")
    plain = eval_mod.bucket_verdict(two_tasks(), "S")
    return verdict["costDiff"] > plain["costDiff"], (verdict["costDiff"], plain["costDiff"])


def case_verdict_unknown_exhausted_spend_is_could_not_tell(tmp):
    rows = two_tasks()
    rows.append({"task": "a", "bucket": "S", "arm": "crew", "attempt": 2, "runStatus": "unscorable",
                 "costUsd": UNKNOWN, "unscoredSpendUsd": UNKNOWN})
    return eval_mod.bucket_verdict(rows, "S")["verdict"] == "could not tell", None


def case_verdict_keeps_regressions_beside_it_and_excludes_contaminated(tmp):
    rows = two_tasks()
    for r in rows:
        if r["arm"] == "crew":
            r["regressionTestsFailed"] = 3
    rows += runs("c", "crew", "S", 9, [99, 99], runStatus="contaminated")
    rows[-1]["runStatus"] = "contaminated"
    verdict = eval_mod.bucket_verdict(rows, "S")
    text = eval_mod.report_text(rows)
    ok = (verdict["regressions"]["crew"] == 3 and verdict["breakEvenUsd"] == 3.0
          and verdict["contaminated"] and "crew 3, baseline 0" in text and "Contaminated runs (excluded)" in text)
    return ok, text


def case_report_total_cost_is_unknown_when_any_run_is_unknown(tmp):
    rows = two_tasks()
    rows[0]["costUsd"] = UNKNOWN
    text = eval_mod.report_text(rows)
    return "total cost: UNKNOWN" in text, text


# --------------------------------------------------------------------------
# the real method files and the CLI

def case_the_real_method_files_exist_and_parse(tmp):
    arms = eval_mod.check_method(REAL_EVAL_DIR)
    return set(arms) == {"crew", "baseline"}, list(arms)


def case_every_real_task_loads(tmp):
    for task_dir in eval_mod.task_dirs(os.path.join(REAL_EVAL_DIR, "tasks")):
        task = eval_mod.load_task(task_dir)
        if task["bucket"] not in eval_mod.BUCKETS:
            return False, task["name"]
    return True, None


def case_cli_report_runs_on_a_results_file(tmp):
    path = os.path.join(tmp, "results.jsonl")
    for r in two_tasks():
        eval_mod.append_result(path, r)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = eval_mod.main(["report", "--results", path])
    return code == 0 and "## Bucket S" in out.getvalue(), out.getvalue()[:200]


def case_cli_refuses_without_a_task_selection(tmp):
    fix = Fix(tmp)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = eval_mod.main(["--tasks-dir", fix.task_root, "--eval-dir", REAL_EVAL_DIR, "validate"])
    return code == 2 and "--task or pass --all" in err.getvalue(), err.getvalue()


# The case names read as sentences; wrapping them would make the table harder to scan.
# --------------------------------------------------------------------------
# L-0851 successor plan: infra is not a defect, the paid row is always written, the cap is scored

def raises_infra(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except eval_mod.GradingInfra as exc:
        return str(exc)
    return None


def case_a_grading_container_that_fails_to_run_is_infra_not_missing_tests(tmp):
    got = {}
    for code in (125, 126, 127):
        task = {"testCommand": ["python3", "-c", f"import sys; sys.exit({code})"]}
        got[code] = raises_infra(eval_mod.run_tests, task, tmp, ["tests/x.py::a"])
    missing_docker = raises_infra(eval_mod.run_tests, {"testCommand": ["true"]}, tmp, ["tests/x.py::a"],
                                  os.path.join(tmp, "no-such-docker"))
    ok = all(message and "exit" in message for message in got.values()) and bool(missing_docker)
    return ok, (got, missing_docker)


def case_an_ungrouped_hidden_test_is_unscored_in_grading_and_refused_by_validate(tmp):
    fix = Fix(tmp)
    task = fix.load()
    frozen = os.path.join(task["dir"], "grading", "tests", "test_calc.py.frozen")
    write(frozen, slurp(frozen) + "\n\ndef test_loose():\n    assert False\n")
    problems = eval_mod.validate_task(task, fix.src)
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
    write(os.path.join(run["repo"], "calc.py"), CALC_BASE + "\n\ndef mul(a, b):\n    return a * b\n")
    result = eval_mod.grade(task, run["repo"], fix.src)
    refused_loose = any("no defect group" in p and "test_loose" in p for p in problems)
    within = result["escapedDefects"] <= result["defectsTotal"]
    ok = refused_loose and result["escapedDefects"] == 0 and within
    return ok, (problems, result)


def case_an_events_file_without_a_completed_turn_makes_codex_usage_unknown(tmp):
    repo, home = codex_events(tmp, [], sessions=0)
    write(os.path.join(repo, "codex-events.jsonl"), json.dumps({"type": "thread.started", "thread_id": "t1"}) + "\n"
          + json.dumps({"type": "turn.failed"}) + "\n")
    tokens, cost = eval_mod.codex_usage(repo, home, "gpt-6-sol")
    return tokens == UNKNOWN and cost == UNKNOWN, (tokens, cost)


def case_a_results_row_without_attempt_is_refused(tmp):
    path = os.path.join(tmp, "results-noattempt.jsonl")
    write(path, json.dumps({"task": "a", "bucket": "S", "arm": "crew", "runStatus": "contaminated"}) + "\n")
    message = refused(eval_mod.read_results, path)
    return bool(message and "attempt" in message), message


def case_a_paid_grading_infra_row_keeps_its_spend_for_the_paired_cost(tmp):
    fix = Fix(tmp)
    saved = eval_mod.grade

    def always_infra(*_args):
        raise eval_mod.GradingInfra("grading container exited 125")
    eval_mod.grade = always_infra
    try:
        fix.env.update({"STUB_MODE": "ok", "STUB_RESULT": "No findings."})
        ctx = fix.ctx()
        with patched_env(fix.env):
            row = eval_mod.run_chain(ctx, fix.load(), fix.arm)
    finally:
        eval_mod.grade = saved
    rows = eval_mod.read_results(fix.results)
    ok = row["runStatus"] == "infra" and rows[0].get("unscoredSpendUsd") == rows[0]["ownCostUsd"] and len(rows) == 1
    return ok, rows


def case_wrong_shape_auth_json_is_a_refusal_not_a_traceback(tmp):
    got = []
    for func in (eval_mod.strip_codex_auth, eval_mod.strip_claude_auth):
        source = os.path.join(tmp, func.__name__ + ".json")
        write(source, "[]")
        got.append(refused(func, source, os.path.join(tmp, "dest.json")))
    return all(got), got


def case_hidden_regression_tests_are_graded_and_may_not_overlap_other_groups(tmp):
    fix = Fix(tmp)
    fix.task["hiddenRegression"] = ["tests/test_calc.py::test_mul"]
    write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
    message = refused(fix.load)
    fix2 = Fix(tmp + "-b")
    fix2.task["hiddenRegression"] = ["tests/test_calc.py::test_loose_pass"]
    frozen = os.path.join(fix2.task_dir, "grading", "tests", "test_calc.py.frozen")
    write(frozen, slurp(frozen) + "\n\ndef test_loose_pass():\n    assert False\n")
    write(os.path.join(fix2.task_dir, "task.json"), json.dumps(fix2.task))
    task = fix2.load()
    run = eval_mod.prepare_run(task, fix2.arm, fix2.src, fix2.runs, 1, os.path.join(fix2.tmp, "plugin-crew"), fix2.env)
    write(os.path.join(run["repo"], "calc.py"), CALC_BASE + "\n\ndef mul(a, b):\n    return a * b\n")
    result = eval_mod.grade(task, run["repo"], fix2.src)
    return bool(message and "hiddenRegression" in message) and result["regressionTestsFailed"] == 1, (message, result)


def case_an_unscored_hidden_test_is_not_counted_but_must_pass_at_reference(tmp):
    fix = Fix(tmp)
    fix.task["unscoredHidden"] = ["tests/test_calc.py::test_loose"]
    write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
    frozen = os.path.join(fix.task_dir, "grading", "tests", "test_calc.py.frozen")
    write(frozen, slurp(frozen) + "\n\ndef test_loose():\n    assert True\n")
    task = fix.load()
    problems = eval_mod.validate_task(task, fix.src)
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
    write(os.path.join(run["repo"], "calc.py"), CALC_BASE + "\n\ndef mul(a, b):\n    return a * b\n")
    graded_ok = eval_mod.grade(task, run["repo"], fix.src)
    write(frozen, slurp(frozen).replace("assert True", "assert False"))
    broken = eval_mod.validate_task(fix.load(), fix.src)
    ok = (problems == [] and graded_ok["escapedDefects"] == 0
          and any("unscoredHidden" in p and "reference" in p for p in broken))
    return ok, (problems, graded_ok, broken)


def case_a_task_with_an_escaping_statement_path_or_unlisted_test_file_is_refused(tmp):
    got = []
    fix = Fix(tmp)
    fix.task["statementFile"] = "../statement.md"
    write(os.path.join(os.path.dirname(fix.task_dir), "statement.md"), "outside the task directory\n")
    write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
    message = refused(fix.load)
    got.append(bool(message and "inside the task directory" in message))
    fix2 = Fix(tmp + "-b")
    fix2.task["testCommand"] = [a for a in fix2.task["testCommand"] if a != "tests/test_calc.py"]
    write(os.path.join(fix2.task_dir, "task.json"), json.dumps(fix2.task))
    got.append(refused(fix2.load))
    return all(got), got


def case_a_second_attempt_that_ends_in_grading_infra_keeps_the_whole_chain_spend(tmp):
    fix = Fix(tmp)
    saved = eval_mod.grade
    calls = []

    def infra_on_second(*args):
        calls.append(1)
        raise eval_mod.GradingInfra("exited 125")
    eval_mod.grade = infra_on_second
    try:
        fix.env.update({"STUB_MODE": "fail-first", "STUB_RESULT": "No findings."})
        ctx = fix.ctx()
        with patched_env(fix.env):
            eval_mod.run_chain(ctx, fix.load(), fix.arm)
    finally:
        eval_mod.grade = saved
    rows = eval_mod.read_results(fix.results)
    last = rows[-1]
    ok = (len(rows) == 2 and rows[0]["runStatus"] == "unscorable" and last["runStatus"] == "infra"
          and eval_mod.known(last.get("unscoredSpendUsd")) and eval_mod.known(rows[0].get("unscoredSpendUsd")))
    return ok, rows


def case_an_arm_settings_object_can_add_but_never_remove_the_web_denials(tmp):
    got = [eval_mod.merged_settings({"permissions": {}})["permissions"]["deny"],
           eval_mod.merged_settings({"permissions": {"deny": ["Bash(rm:*)"]}})["permissions"]["deny"],
           eval_mod.merged_settings({"permissions": None})["permissions"]["deny"],
           eval_mod.merged_settings({})["permissions"]["deny"]]
    want = ["WebFetch", "WebSearch"]
    ok = got == [want, want + ["Bash(rm:*)"], want, want]
    return ok, got


def case_a_wrong_shape_arm_file_is_refused_before_any_run(tmp):
    bad = [("baseline", ["reviewParse"], None), ("baseline", ["reviewParse", "findings"], 5),
           ("baseline", ["reviewParse", "noFindings"], "("), ("baseline", ["cli", "args"], "--model x"),
           ("baseline", ["cli", "maxCycles"], -1), ("baseline", ["prompts", "review"], None),
           ("baseline", ["settings"], []), ("baseline", ["settings"], {"permissions": {"deny": "WebFetch"}}),
           ("baseline", ["proxyIgnoreHosts"], "github.com"), ("baseline", ["author"], None),
           ("crew", ["crewConfig"], []), ("crew", ["assignment"], {"template": 1, "risk": "med"}),
           ("crew", ["reviewer"], {"tool": "x"}), ("crew", ["cli", "maxResumes"], "3"),
           ("baseline", ["arm"], "other"), ("crew", ["removePaths"], "x"), ("crew", ["removePaths"], ["/etc"]),
           ("crew", ["removePaths"], ["../x"]), ("crew", ["removePaths"], [""]),
           ("crew", ["removePaths"], ["..\\x"]), ("crew", ["removePaths"], ["."])]
    got = []
    for number, (name, keys, value) in enumerate(bad):
        arm = json.loads(slurp(os.path.join(REAL_EVAL_DIR, "arms", name + ".json")))
        node = arm
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
        path = os.path.join(tmp, f"arm{number}.json")
        write(path, json.dumps(arm))
        got.append(bool(refused(eval_mod.load_arm, path)))
    return all(got), got


def case_a_clock_that_expires_between_invocations_ends_the_arm_as_wall_clock(tmp):
    fix = Fix(tmp)
    state = os.path.join(tmp, "stub-state")
    fix.env.update({"STUB_MODE": "ok", "STUB_RESULT": "No findings."})
    ctx = fix.ctx()
    ctx["clock"] = lambda: 10 ** 9 if os.path.exists(state) else 0
    with patched_env(fix.env):
        task = fix.load()
        run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(fix.tmp, "plugin-crew"), fix.env)
        driven = eval_mod.drive_arm(ctx["docker"], run, task, fix.arm, ctx["clock"])
    return driven["endedBy"] == "wall-clock", driven


def case_validate_all_fails_on_a_task_directory_without_task_json(tmp):
    root = os.path.join(tmp, "tasks")
    os.makedirs(os.path.join(root, "t-broken"))
    write(os.path.join(root, "notes.md"), "not a task\n")
    message = refused(eval_mod.task_dirs, root)
    return bool(message and "no task.json" in message), message


def case_a_scored_retry_chain_costs_the_whole_chain_and_the_task_uses_the_median_of_chains(tmp):
    def row(task, arm, attempt, status, own, cost, defects=None, spend=None):
        out = {"task": task, "bucket": "S", "arm": arm, "attempt": attempt, "runStatus": status, "ownCostUsd": own,
               "costUsd": cost, "escapedDefects": defects, "regressionTestsFailed": 0 if defects is not None else None}
        if spend is not None:
            out["unscoredSpendUsd"] = spend
        return out
    rows = []
    for task in ("a", "b"):
        for arm, defects in (("baseline", 1), ("crew", 0)):
            if arm == "crew" and task == "a":
                rows.append(row(task, arm, 1, "unscorable", 3.0, 3.0, spend=3.0))
                rows.append(row(task, arm, 2, "scored", 2.0, 5.0, defects))
            else:
                rows.append(row(task, arm, 1, "scored", 2.0 if arm == "crew" else 1.0, 2.0 if arm == "crew" else 1.0,
                                defects))
            rows.append(row(task, arm, 1, "scored", 2.0 if arm == "crew" else 1.0, 2.0 if arm == "crew" else 1.0,
                            defects))
    result = eval_mod.bucket_verdict(rows, "S")
    return result.get("costDiff") == 1.75, result


def case_transcripts_reached_through_a_symlink_make_usage_unknown(tmp):
    home = transcript_home(tmp, [assistant("m1", 1000)])
    outside = os.path.join(tmp, "host-project")
    write(os.path.join(outside, "other.jsonl"), json.dumps(assistant("m9", 5000)) + "\n")
    os.symlink(outside, os.path.join(home, ".claude", "projects", "planted"))
    tokens, cost, _ = eval_mod.claude_usage(home)
    return tokens == UNKNOWN and cost == UNKNOWN, (tokens, cost)


def case_a_non_finite_wall_clock_limit_is_refused(tmp):
    arm = json.loads(slurp(os.path.join(REAL_EVAL_DIR, "arms", "baseline.json")))
    path = os.path.join(tmp, "arm.json")
    write(path, json.dumps(arm).replace('"S": 30', '"S": 1e999').replace('"S": 60', '"S": 1e999'))
    message = refused(eval_mod.load_arm, path)
    return bool(message), message


def case_run_validates_every_task_before_any_billed_work(tmp):
    fix = Fix(tmp)
    fix.task["reference"] = "0" * 40
    write(os.path.join(fix.task_dir, "task.json"), json.dumps(fix.task))
    write(os.path.join(os.path.dirname(fix.results), "canary.txt"), "PASS something\ncanary: PASS\n")
    errors = io.StringIO()
    with patched_env(fix.env), contextlib.redirect_stderr(errors):
        code = eval_mod.main(["--tasks-dir", fix.task_root, "--eval-dir", REAL_EVAL_DIR, "--source-repo", fix.src,
                              "run", "--task", fix.task["name"], "--results", fix.results, "--runs-dir", fix.runs])
    ran = os.path.exists(fix.results) or os.path.isdir(fix.runs) and bool(os.listdir(fix.runs))
    return code == 2 and "do not validate" in errors.getvalue() and not ran, (code, errors.getvalue()[:300], ran)


def case_two_task_directories_with_one_name_are_refused(tmp):
    fix = Fix(tmp)
    shutil.copytree(fix.task_dir, os.path.join(fix.task_root, "copy-of-task"))
    args = argparse.Namespace(tasks_dir=fix.task_root, task=None, all=True)
    message = refused(eval_mod.selected_tasks, args)
    return bool(message and "share a task name" in message), message


def case_a_results_row_with_an_unknown_arm_bucket_or_status_is_refused(tmp):
    got = []
    for patch in ({"arm": "creww"}, {"bucket": "XL"}, {"runStatus": "maybe"}):
        path = os.path.join(tmp, f"results-{next(iter(patch))}.jsonl")
        row = {"task": "a", "bucket": "S", "arm": "crew", "runStatus": "scored", "attempt": 1, **patch}
        write(path, json.dumps(row) + "\n")
        got.append(bool(refused(eval_mod.read_results, path)))
    return all(got), got


def case_a_paid_unscorable_row_without_recorded_spend_is_unknown_not_zero(tmp):
    rows = two_tasks()
    rows.append({"task": "a", "bucket": "S", "arm": "crew", "attempt": 1, "runStatus": "unscorable", "ownCostUsd": 10.0,
                 "costUsd": 10.0})
    result = eval_mod.bucket_verdict(rows, "S")
    rows2 = two_tasks()
    rows2.append({"task": "a", "bucket": "S", "arm": "crew", "attempt": 1, "runStatus": "unscorable"})
    result2 = eval_mod.bucket_verdict(rows2, "S")
    clean = eval_mod.bucket_verdict(two_tasks(), "S")
    ok = result.get("costDiff", 0) > clean["costDiff"] and any("UNKNOWN" in line for line in result2["lines"])
    return ok, (clean.get("costDiff"), result.get("costDiff"), result2["lines"])


def case_a_symlink_alias_of_the_results_file_shares_one_lock(tmp):
    path = os.path.join(tmp, "results.jsonl")
    write(path, "")
    alias = os.path.join(tmp, "alias.jsonl")
    os.symlink(path, alias)
    first = eval_mod.lock_results(path)
    try:
        message = refused(eval_mod.lock_results, alias)
    finally:
        first.close()
    return bool(message and "another run" in message), message


def case_a_fabricated_third_attempt_row_is_refused(tmp):
    path = os.path.join(tmp, "results-a3.jsonl")
    write(path, json.dumps({"task": "a", "bucket": "S", "arm": "crew", "runStatus": "scored", "attempt": 3}) + "\n")
    message = refused(eval_mod.read_results, path)
    return bool(message and "attempt" in message), message


def case_a_missing_pinned_protocol_limit_in_an_arm_is_refused(tmp):
    got = []
    for name, key in (("crew", "maxResumes"), ("baseline", "maxCycles")):
        arm = json.loads(slurp(os.path.join(REAL_EVAL_DIR, "arms", name + ".json")))
        del arm["cli"][key]
        path = os.path.join(tmp, name + ".json")
        write(path, json.dumps(arm))
        message = refused(eval_mod.load_arm, path)
        got.append(bool(message and "pinned" in message))
    return all(got), got


def case_a_scored_row_with_a_wrong_type_cost_is_refused(tmp):
    path = os.path.join(tmp, "results-cost.jsonl")
    write(path, json.dumps({"task": "a", "bucket": "S", "arm": "crew", "runStatus": "scored", "attempt": 1,
                            "costUsd": "oops"}) + "\n")
    message = refused(eval_mod.read_results, path)
    return bool(message and "costUsd" in message), message


def case_an_exception_in_the_arm_driver_still_writes_a_paid_row(tmp):
    fix = Fix(tmp)
    saved = eval_mod.drive_arm

    def half_done(*args):
        args[-1]["sessions"] = ["sess-1"]
        raise RuntimeError("docker vanished")
    eval_mod.drive_arm = half_done
    try:
        result, _ = run_arm(fix, "ok", STUB_RESULT="No findings.")
    finally:
        eval_mod.drive_arm = saved
    return result["runStatus"] == "unscorable" and "arm driver raised" in (result["failure"] or ""), result


def case_a_grading_infra_failure_is_retried_once_before_the_run_is_unscored(tmp):
    fix = Fix(tmp)
    calls = []
    saved = eval_mod.grade

    def flaky(*args):
        calls.append(1)
        if len(calls) == 1:
            raise eval_mod.GradingInfra("grading container exited 125")
        return saved(*args)
    eval_mod.grade = flaky
    try:
        result, _ = run_arm(fix, "ok", STUB_RESULT="No findings.")
    finally:
        eval_mod.grade = saved
    return result["runStatus"] == "scored" and len(calls) == 2, (result["runStatus"], len(calls))


def case_a_stalled_or_failed_run_dir_chown_refuses_before_any_paid_work(tmp):
    saved = eval_mod.chown_tree
    eval_mod.chown_tree = lambda *a: "gave no answer in 300s"
    fix = Fix(tmp)
    saved_geteuid = os.geteuid
    os.geteuid = lambda: 0
    try:
        task = fix.load()
        message = refused(eval_mod.prepare_run, task, fix.arm, fix.src, fix.runs, 1,
                          os.path.join(fix.tmp, "plugin-crew"), fix.env)
    finally:
        os.geteuid = saved_geteuid
        eval_mod.chown_tree = saved
    return bool(message and "chown" in message), message


def case_contamination_reads_the_probe_events_file(tmp):
    fix = Fix(tmp)
    task = fix.load()
    home = os.path.join(tmp, "home")
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(home, ".claude", "projects"))
    write(os.path.join(repo, ".work", "review", "x", "probe-events.jsonl"),
          json.dumps({"text": task["reference"]}) + "\n")
    reasons = eval_mod.contamination(task, home, repo, os.path.join(tmp, "none.jsonl"), fix.arm, fix.src)
    return "reference sha" in reasons, reasons


def case_t_0108_names_its_reference_pr(tmp):
    task = eval_mod.read_json(os.path.join(REAL_EVAL_DIR, "tasks", "t-0108-nuclei-safe-defaults", "task.json"))
    return task.get("referencePr") == 451, task.get("referencePr")


def case_an_errored_baseline_review_is_incomplete_and_retried_once(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "fail-second", STUB_RESULT="No findings.")
    ok = result["runStatus"] == "scored" and result["reviewAttemptsIncomplete"] == 1 and result["reviewCycles"] == 1
    return ok, result


def case_a_failed_autopilot_probe_is_a_harness_failure_not_a_stop(tmp):
    fix = Fix(tmp)
    arm = eval_mod.load_arm(os.path.join(REAL_EVAL_DIR, "arms", "crew.json"))
    saved = eval_mod.autopilot_stopped
    eval_mod.autopilot_stopped = lambda shell, ticket: None
    try:
        result, _ = run_arm(fix, "ok", arm=arm, STUB_RESULT="working")
    finally:
        eval_mod.autopilot_stopped = saved
    return result["runStatus"] == "unscorable" and "probe" in (result["failure"] or ""), result


def case_a_contamination_check_that_raises_still_writes_a_row(tmp):
    fix = Fix(tmp)
    saved = eval_mod.contamination

    def boom(*_args):
        raise eval_mod.EvalError("git show timed out")
    eval_mod.contamination = boom
    try:
        result, _ = run_arm(fix, "ok", STUB_RESULT="No findings.")
    finally:
        eval_mod.contamination = saved
    return result["runStatus"] == "error" and "contamination check" in (result["failure"] or ""), result


def case_a_wrong_shape_wall_clock_is_a_refusal_not_a_traceback(tmp):
    results = []
    for bad in (1, {"S": 1, "M": 2, "L": -3}, {"S": True, "M": 2, "L": 3}):
        arm_dir = os.path.join(tmp, f"arm{len(results)}")
        os.makedirs(arm_dir)
        arm = json.loads(slurp(os.path.join(REAL_EVAL_DIR, "arms", "baseline.json")))
        arm["wallClockMinutes"] = bad
        write(os.path.join(arm_dir, "a.json"), json.dumps(arm))
        results.append(refused(eval_mod.load_arm, os.path.join(arm_dir, "a.json")))
    return all(results), results


def case_codex_counts_that_cannot_be_true_make_usage_unknown(tmp):
    got = []
    for patch in ({"cached_input_tokens": USAGE["input_tokens"] + 5}, {"input_tokens": -1}):
        repo, home = codex_events(tmp, [dict(USAGE, **patch)], sessions=1)
        got.append(eval_mod.codex_usage(repo, home, "gpt-6-sol")[0] == UNKNOWN)
    return all(got), got


def case_a_failed_chown_of_the_grading_copy_is_infra_not_a_defect(tmp):
    saved = eval_mod.container_user
    eval_mod.container_user = lambda: ("1000", "1000", True)
    try:
        message = raises_infra(eval_mod.run_tests, {"testCommand": ["true"]}, os.path.join(tmp, "no-such-repo"),
                               ["tests/x.py::a"], os.path.join(tmp, "no-such-docker"))
    finally:
        eval_mod.container_user = saved
    return bool(message and "chown" in message), message


def case_malformed_optional_codex_counts_make_usage_unknown(tmp):
    got = []
    for bad in (None, True, "5"):
        usage = dict(USAGE, cached_input_tokens=bad)
        if bad is None:
            usage.pop("cached_input_tokens")
            got.append(True)
            continue
        repo, home = codex_events(tmp, [usage], sessions=1)
        got.append(eval_mod.codex_usage(repo, home, "gpt-6-sol")[0] == UNKNOWN)
    return all(got), got


def case_a_wrong_shape_results_row_is_refused_not_a_crash(tmp):
    path = os.path.join(tmp, "results-bad.jsonl")
    write(path, json.dumps({"bucket": "S", "runStatus": "scored", "arm": "crew", "attempt": 1, "task": []}) + "\n")
    try:
        eval_mod.read_results(path)
    except eval_mod.EvalError as exc:
        return "present strings" in str(exc), str(exc)
    return False, "accepted"


def case_a_git_that_never_answers_is_bounded(tmp):
    stub = os.path.join(tmp, "hang-git")
    write(stub, "#!/bin/sh\nexec sleep 30\n", EXEC)
    saved = (os.environ.get("CREW_OUTCOME_GIT"), eval_mod.GIT_TIMEOUT_SECONDS)
    os.environ["CREW_OUTCOME_GIT"] = stub
    eval_mod.GIT_TIMEOUT_SECONDS = 1
    started = time.monotonic()
    try:
        eval_mod.git("status")
        message = None
    except eval_mod.EvalError as exc:
        message = str(exc)
    finally:
        eval_mod.GIT_TIMEOUT_SECONDS = saved[1]
        if saved[0] is None:
            del os.environ["CREW_OUTCOME_GIT"]
        else:
            os.environ["CREW_OUTCOME_GIT"] = saved[0]
    return bool(message and "no answer" in message) and time.monotonic() - started < 15, message


def case_a_docker_rm_that_hangs_after_a_grading_timeout_does_not_hang_the_run(tmp):
    docker = os.path.join(tmp, "hang-docker")
    write(docker, "#!/bin/sh\ncase \"$1\" in run) exec sleep 30;; rm) exec sleep 30;; esac\n", EXEC)
    saved = (eval_mod.TEST_TIMEOUT_SECONDS, eval_mod.CLEANUP_TIMEOUT_SECONDS)
    eval_mod.TEST_TIMEOUT_SECONDS = eval_mod.CLEANUP_TIMEOUT_SECONDS = 1
    started = time.monotonic()
    try:
        message = raises_infra(eval_mod.run_tests, {"testCommand": ["true"]}, tmp, ["tests/x.py::a"], docker)
    finally:
        eval_mod.TEST_TIMEOUT_SECONDS, eval_mod.CLEANUP_TIMEOUT_SECONDS = saved
    elapsed = time.monotonic() - started
    return bool(message and "timed out" in message) and elapsed < 15, (message, elapsed)


def run_chain_with_grade(fix, grade_func, mode="ok"):
    fix.env.update({"STUB_MODE": mode, "STUB_RESULT": "No findings."})
    ctx = fix.ctx()
    saved = eval_mod.grade
    eval_mod.grade = grade_func
    try:
        with patched_env(fix.env):
            final = eval_mod.run_chain(ctx, fix.load(), fix.arm)
    finally:
        eval_mod.grade = saved
    return final, eval_mod.read_results(fix.results)


def case_a_grading_infra_failure_is_an_unscored_infra_row_with_its_cost_and_no_rerun(tmp):
    def infra(*_args, **_kwargs):
        raise eval_mod.GradingInfra("grading container exited 125")

    final, rows = run_chain_with_grade(Fix(tmp), infra)
    ok = (len(rows) == 1 and final["runStatus"] == "infra" and final["escapedDefects"] is None
          and final["regressionTestsFailed"] is None and final["ownCostUsd"] > 0
          and "exited 125" in final["failure"])
    return ok, rows


def case_a_grading_exception_still_writes_a_row_with_the_paid_cost(tmp):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom in grading")

    final, rows = run_chain_with_grade(Fix(tmp), boom)
    ok = (len(rows) == 1 and final["runStatus"] == "error" and final["ownCostUsd"] > 0
          and final["escapedDefects"] is None and "boom in grading" in final["failure"])
    return ok, rows


def case_a_scored_run_still_grades_through_the_same_wrapper(tmp):
    final, rows = run_chain_with_grade(Fix(tmp), eval_mod.grade)
    return len(rows) == 1 and final["runStatus"] == "scored" and final["escapedDefects"] == 0, rows


def case_an_infra_or_error_row_makes_its_bucket_could_not_tell_and_is_named(tmp):
    rows = two_tasks() + [{"task": "c", "bucket": "S", "arm": "crew", "attempt": 1, "runStatus": "infra",
                           "escapedDefects": None, "costUsd": 2.0, "ownCostUsd": 2.0,
                           "failure": "grading container exited 125"}]
    verdict = eval_mod.bucket_verdict(rows, "S")
    plain = eval_mod.bucket_verdict(two_tasks(), "S")
    ok = (verdict["verdict"] == "could not tell" and "unscored" in " ".join(verdict["lines"])
          and plain["verdict"] == "break-even")
    return ok, (verdict, plain["verdict"])


def case_a_crew_run_that_hits_the_resume_cap_is_graded_and_marked(tmp):
    fix = Fix(tmp)
    arm = eval_mod.load_arm(os.path.join(REAL_EVAL_DIR, "arms", "crew.json"))
    result, _ = run_arm(fix, "ok", arm=arm, STUB_RESULT="working")
    text = eval_mod.report_text([result])
    ok = (result["runStatus"] == "scored" and result["endedBy"] == "resume-cap"
          and "resume cap" in text)
    return ok, (result["runStatus"], result.get("endedBy"), text)


def case_a_run_that_stops_on_its_own_is_not_marked_as_capped(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "ok", STUB_RESULT="No findings.")
    return result["runStatus"] == "scored" and result["endedBy"] != "resume-cap", result.get("endedBy")


def case_a_cli_that_exits_nonzero_with_ok_json_is_unscorable(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "exit3-ok-json", STUB_RESULT="No findings.")
    return result["runStatus"] == "unscorable" and "exited 3" in (result["failure"] or ""), result["failure"]


def case_a_cli_json_without_a_session_id_is_unscorable(tmp):
    fix = Fix(tmp)
    result, _ = run_arm(fix, "no-session-id", STUB_RESULT="No findings.")
    return result["runStatus"] == "unscorable" and "session_id" in (result["failure"] or ""), result["failure"]


def case_a_completed_codex_turn_without_usage_makes_usage_unknown(tmp):
    repo, home = codex_events(tmp, [USAGE], sessions=1)
    write(os.path.join(repo, ".work", "review", "r0", "codex-events.jsonl"),
          json.dumps({"type": "thread.started", "thread_id": "thread-0"}) + "\n"
          + json.dumps({"type": "turn.completed", "usage": USAGE}) + "\n"
          + json.dumps({"type": "turn.completed"}) + "\n")
    got = eval_mod.codex_usage(repo, home, "m")
    return got == (UNKNOWN, UNKNOWN), got


def case_a_bare_reference_pr_number_is_flagged_but_a_longer_number_is_not(tmp):
    def reasons_for(name, text):
        base = os.path.join(tmp, name)
        os.makedirs(base)
        return run_with_text(Fix(base), text)

    flagged = [reasons_for(f"f{n}", text) for n, text in enumerate(
        ("see #4242 for the fix", "https://github.com/x/y/pull/4242/files", "PR #4242.", "x/y#4242"))]
    clean = [reasons_for(f"c{n}", text) for n, text in enumerate(
        ("issue #42420", "https://github.com/x/y/pull/42420", "colour #4242a1", "id 14242 and &#4242;"))]
    ok = (flagged == [["reference PR number"], ["reference PR URL"], ["reference PR number"], ["reference PR number"]]
          and all(r == [] for r in clean))
    return ok, (flagged, clean)


def case_hidden_test_lines_spread_over_separate_files_do_not_flag_a_run(tmp):
    fix = Fix(tmp)
    task = fix.load()
    run = eval_mod.prepare_run(task, fix.arm, fix.src, fix.runs, 1, os.path.join(tmp, "plugin-crew"), fix.env)
    log = os.path.join(run["proxylog"], "proxy.jsonl")
    write(log, "")
    for n, line in enumerate((LONG1, LONG2, LONG3)):
        write(os.path.join(run["home"], ".claude", "projects", "-run-repo", f"s{n}.jsonl"),
              json.dumps({"text": line}) + "\n")
    spread = eval_mod.contamination(task, run["home"], run["repo"], log, fix.arm, fix.src)
    write(os.path.join(run["home"], ".claude", "projects", "-run-repo", "one.jsonl"),
          json.dumps({"text": LONG1 + "\n" + LONG2 + "\n" + LONG3}) + "\n")
    together = eval_mod.contamination(task, run["home"], run["repo"], log, fix.arm, fix.src)
    return spread == [] and together == ["hidden test content"], (spread, together)


def case_the_claude_auth_copy_is_an_allowlist_of_oauth_fields(tmp):
    source = os.path.join(tmp, "creds.json")
    write(source, json.dumps({"claudeAiOauth": {"accessToken": "AT", "refreshToken": "RT", "expiresAt": 1,
                                                 "scopes": ["user:inference"], "subscriptionType": "max",
                                                 "apiKey": "OTHER-SECRET", "cloudToken": "CLOUD-SECRET"}}))
    dest = os.path.join(tmp, "out", "creds.json")
    eval_mod.strip_claude_auth(source, dest)
    blob = slurp(dest)
    kept = json.loads(blob)["claudeAiOauth"]
    ok = ("OTHER-SECRET" not in blob and "CLOUD-SECRET" not in blob and "RT" not in kept.values()
          and kept["accessToken"] == "AT" and kept["expiresAt"] == 1 and kept["scopes"] == ["user:inference"])
    return ok, blob


# pylint: disable=line-too-long
CASES = (
    ("must-allow: validate accepts a task whose hidden tests fail at base and pass at reference", case_validate_accepts_a_good_task),
    ("must-block: validate refuses hidden tests that pass at base", case_validate_refuses_hidden_tests_that_pass_at_base),
    ("must-block: validate refuses hidden tests that fail at reference", case_validate_refuses_hidden_tests_that_fail_at_reference),
    ("must-block: validate refuses an unresolvable reference sha", case_validate_refuses_an_unreachable_reference_sha),
    ("must-block: a task with overlapping defects does not load", case_load_refuses_overlapping_defects),
    ("must-allow: the run repo is one commit and cannot resolve the reference or base", case_run_repo_is_one_commit_without_the_reference),
    ("must-block: prepare refuses when the reference is reachable", case_prepare_refuses_when_the_reference_is_reachable),
    ("must-allow: hidden tests are absent from the repo during the arm", case_hidden_tests_are_absent_during_the_arm),
    ("must-allow: auth copies lack refresh tokens and nothing else of the owner's is copied", case_auth_files_carry_no_refresh_token_and_nothing_else_of_the_owners),
    ("must-allow: docker run mounts only the run repo and homes", case_docker_argv_mounts_only_the_run_dirs),
    ("must-allow: grading a correct run finds no escape", case_grading_scores_a_correct_run_with_no_escapes),
    ("must-block: a defect escapes when any of its tests fails", case_grading_counts_a_defect_when_any_of_its_tests_fail),
    ("must-allow: a hidden file that cannot import does not fail the visible tests", case_a_hidden_file_that_cannot_import_does_not_fail_the_visible_tests),
    ("must-allow: an edited conftest.py is restored for grading", case_an_edited_conftest_is_restored_for_grading),
    ("must-allow: a deleted visible test is restored for grading", case_a_deleted_visible_test_is_restored_for_grading),
    ("must-block: a skipped hidden test counts as failed", case_a_skipped_hidden_test_counts_as_failed),
    ("must-block: a hidden test that is not collected counts as failed", case_a_test_that_is_not_collected_counts_as_failed),
    ("must-allow: Claude cost counts subagent files and each message once", case_claude_cost_counts_subagent_files_and_each_message_once),
    ("must-block: a missing subagent transcript makes cost UNKNOWN", case_a_missing_subagent_transcript_makes_cost_unknown),
    ("must-block: an unparseable transcript makes usage UNKNOWN", case_an_unparseable_transcript_makes_usage_unknown),
    ("must-block: an unpriced model makes cost UNKNOWN", case_an_unpriced_model_makes_cost_unknown),
    ("must-block: no transcripts is UNKNOWN, not zero", case_no_transcripts_is_unknown_not_zero),
    ("must-allow: Codex tokens sum turn.completed usage; an unpriced model is UNKNOWN cost", case_codex_tokens_sum_the_turn_completed_usage),
    ("must-block: a Codex session with no events file makes usage UNKNOWN", case_codex_session_without_an_events_file_makes_usage_unknown),
    ("must-allow: a run with no Codex call costs zero", case_no_codex_call_is_zero_cost),
    ("must-allow: Codex cost is computed from a dated price row", case_codex_cost_uses_a_dated_price_row),
    ("must-allow: the pinned Codex reviewer model has a price row and a known cost", case_pinned_codex_model_has_a_price_row_and_a_known_cost),
    ("must-allow: a wrong-shape review ledger counts as incomplete, never raises", case_crew_rounds_wrong_shape_ledger_is_incomplete_not_an_exception),
    ("must-block: an errored baseline review is incomplete and retried once", case_an_errored_baseline_review_is_incomplete_and_retried_once),
    ("must-block: a failed autopilot probe is a harness failure, not a stop", case_a_failed_autopilot_probe_is_a_harness_failure_not_a_stop),
    ("must-block: a contamination check that raises still writes a row", case_a_contamination_check_that_raises_still_writes_a_row),
    ("must-block: a wrong-shape wallClockMinutes is a refusal", case_a_wrong_shape_wall_clock_is_a_refusal_not_a_traceback),
    ("must-block: Codex counts that cannot be true make usage UNKNOWN", case_codex_counts_that_cannot_be_true_make_usage_unknown),
    ("must-block: an ungrouped hidden test is unscored in grading and refused by validate", case_an_ungrouped_hidden_test_is_unscored_in_grading_and_refused_by_validate),
    ("must-block: an events file without a completed turn makes Codex usage UNKNOWN", case_an_events_file_without_a_completed_turn_makes_codex_usage_unknown),
    ("must-block: a results row without attempt is refused", case_a_results_row_without_attempt_is_refused),
    ("must-block: a paid grading infra row keeps its spend", case_a_paid_grading_infra_row_keeps_its_spend_for_the_paired_cost),
    ("must-block: wrong-shape auth JSON is a refusal", case_wrong_shape_auth_json_is_a_refusal_not_a_traceback),
    ("must-block: hidden regression tests are graded and may not overlap", case_hidden_regression_tests_are_graded_and_may_not_overlap_other_groups),
    ("must-block: an unscored hidden test is not counted but must pass at reference", case_an_unscored_hidden_test_is_not_counted_but_must_pass_at_reference),
    ("must-block: an escaping statement path or unlisted test file is refused", case_a_task_with_an_escaping_statement_path_or_unlisted_test_file_is_refused),
    ("must-block: a second attempt ending in grading infra keeps the chain spend", case_a_second_attempt_that_ends_in_grading_infra_keeps_the_whole_chain_spend),
    ("must-block: arm settings can add but never remove the web denials", case_an_arm_settings_object_can_add_but_never_remove_the_web_denials),
    ("must-block: a wrong-shape arm file is refused before any run", case_a_wrong_shape_arm_file_is_refused_before_any_run),
    ("must-block: a clock that expires between invocations ends the arm as wall-clock", case_a_clock_that_expires_between_invocations_ends_the_arm_as_wall_clock),
    ("must-block: validate --all fails on a task directory without task.json", case_validate_all_fails_on_a_task_directory_without_task_json),
    ("must-block: a scored retry chain costs the whole chain and the task uses the median of chains", case_a_scored_retry_chain_costs_the_whole_chain_and_the_task_uses_the_median_of_chains),
    ("must-block: transcripts reached through a symlink make usage UNKNOWN", case_transcripts_reached_through_a_symlink_make_usage_unknown),
    ("must-block: a non-finite wall-clock limit is refused", case_a_non_finite_wall_clock_limit_is_refused),
    ("must-block: run validates every task before any billed work", case_run_validates_every_task_before_any_billed_work),
    ("must-block: two task directories with one name are refused", case_two_task_directories_with_one_name_are_refused),
    ("must-block: a results row with an unknown arm, bucket or status is refused", case_a_results_row_with_an_unknown_arm_bucket_or_status_is_refused),
    ("must-block: a paid unscorable row without recorded spend is unknown, not zero", case_a_paid_unscorable_row_without_recorded_spend_is_unknown_not_zero),
    ("must-block: a symlink alias of the results file shares one lock", case_a_symlink_alias_of_the_results_file_shares_one_lock),
    ("must-block: a fabricated third attempt row is refused", case_a_fabricated_third_attempt_row_is_refused),
    ("must-block: a missing pinned protocol limit in an arm is refused", case_a_missing_pinned_protocol_limit_in_an_arm_is_refused),
    ("must-block: a scored row with a wrong-type cost is refused", case_a_scored_row_with_a_wrong_type_cost_is_refused),
    ("must-block: an exception in the arm driver still writes a paid row", case_an_exception_in_the_arm_driver_still_writes_a_paid_row),
    ("must-block: a grading infra failure is retried once", case_a_grading_infra_failure_is_retried_once_before_the_run_is_unscored),
    ("must-block: a stalled or failed run-dir chown refuses before paid work", case_a_stalled_or_failed_run_dir_chown_refuses_before_any_paid_work),
    ("must-block: contamination reads probe-events.jsonl", case_contamination_reads_the_probe_events_file),
    ("must-block: T-0108 names its reference PR", case_t_0108_names_its_reference_pr),
    ("must-block: a failed chown of the grading copy is infra, not a defect", case_a_failed_chown_of_the_grading_copy_is_infra_not_a_defect),
    ("must-block: malformed optional Codex counts make usage UNKNOWN", case_malformed_optional_codex_counts_make_usage_unknown),
    ("must-block: a wrong-shape results row is refused, not a crash", case_a_wrong_shape_results_row_is_refused_not_a_crash),
    ("must-block: a git that never answers is bounded", case_a_git_that_never_answers_is_bounded),
    ("must-block: contamination flags the reference sha", case_contamination_flags_the_reference_sha),
    ("must-block: contamination flags the reference PR URL", case_contamination_flags_the_reference_pr_url),
    ("must-allow: README text and the repo path never flag a run", case_contamination_does_not_flag_readme_text_or_the_repo_path),
    ("must-block: three distinctive hidden lines flag a run, fewer do not", case_contamination_flags_hidden_test_content_but_not_a_few_shared_lines),
    ("must-allow: hidden lines the statement itself gives never flag a run", case_contamination_ignores_hidden_lines_the_statement_gives),
    ("must-block: a refused host flags a run, an ignored one does not", case_contamination_flags_a_refused_host_but_not_an_ignored_one),
    ("must-block: the first pilot run is held to the first-run estimate", case_first_pilot_run_uses_the_first_run_estimate),
    ("must-block: budget projects the highest cost seen for the bucket and arm", case_budget_projects_the_highest_observed_cost_for_the_bucket_and_arm),
    ("must-allow: a new bucket falls back to the arm's pilot cost", case_budget_falls_back_to_the_arms_pilot_cost_in_a_new_bucket),
    ("must-block: an UNKNOWN-cost run stops the batch", case_an_unknown_cost_run_stops_the_batch),
    ("must-allow: carried cost is not counted twice against the budget", case_budget_counts_each_attempt_once_not_the_carried_cost),
    ("must-allow: results are appended as full JSON lines", case_results_are_appended_as_full_json_lines),
    ("must-allow: a stub baseline run is scored and costed", case_a_stub_baseline_run_is_scored_and_costed),
    ("must-allow: the baseline loop fixes findings and stops at three cycles", case_a_baseline_run_fixes_findings_then_stops_at_three_cycles),
    ("must-block: an unparseable review is incomplete, not a cycle", case_an_unparseable_review_counts_as_incomplete_not_a_cycle),
    ("must-allow: a run has no docker network at all and reaches only the proxy socket", case_a_stub_run_through_docker_has_no_network_and_reaches_only_the_proxy_socket),
    ("must-block: a run that names the reference is contaminated", case_a_contaminated_run_is_marked_and_still_costed),
    ("must-block: a missing subagent transcript makes the whole run's cost UNKNOWN", case_a_missing_subagent_transcript_makes_the_run_cost_unknown),
    ("must-allow: a paid unscorable attempt keeps its spend on its own row", case_a_paid_unscorable_attempt_is_carried_into_its_rerun),
    ("must-allow: an exhausted paid failure keeps its spend as unscoredSpendUsd", case_an_exhausted_paid_failure_keeps_its_spend),
    ("must-allow: a session's cumulative CLI cost counts once", case_cli_cost_counts_each_session_once_not_cumulatively),
    ("must-allow: every CLI JSON is kept beside the run", case_every_cli_json_is_kept_beside_the_run),
    ("must-block: the argv carries a git identity, drops capabilities, mounts only repo and home, and has no unconfined seccomp or apparmor", case_the_argv_carries_git_identity_and_the_isolation_options),
    ("must-allow: the codex shim rewrites only the read-only sandbox value, and the image puts it first on PATH", case_the_codex_shim_rewrites_only_the_read_only_sandbox),
    ("must-block: only a readable stop=0 keeps the crew arm going", case_autopilot_stopped_only_on_a_readable_stop_0_keeps_going),
    ("must-allow: a crew arm assigns a ticket, resumes while autopilot says stop=0, and a run that hits the resume cap is graded and marked", case_a_crew_arm_assigns_a_ticket_then_resumes_while_autopilot_says_stop_0),
    ("must-block: a crew arm whose assign fails is unscorable", case_a_crew_arm_whose_assign_fails_is_unscorable),
    ("must-block: run needs a passing canary", case_run_refuses_without_a_passing_canary),
    ("must-block: a missing docker is a refusal, never a bare name", case_docker_missing_is_a_refusal_not_a_bare_name),
    ("must-allow: the verdict states the break-even value", case_verdict_states_the_break_even_value),
    ("must-block: no fewer escaped defects when the difference is not negative", case_verdict_says_no_fewer_defects_when_the_difference_is_not_negative),
    ("must-allow: cheaper and fewer defects pays at any value", case_verdict_says_free_when_crew_is_cheaper_and_avoids_defects),
    ("must-block: an empty bucket is could not tell", case_verdict_empty_bucket_is_could_not_tell),
    ("must-block: one task is could not tell", case_verdict_one_task_is_could_not_tell),
    ("must-block: asymmetric missing runs drop the task", case_verdict_drops_a_task_with_fewer_than_two_known_runs_in_an_arm),
    ("must-block: an UNKNOWN cost input is could not tell", case_verdict_unknown_cost_is_could_not_tell),
    ("must-allow: exhausted spend counts in the paired cost difference", case_verdict_exhausted_spend_counts_in_the_paired_cost_difference),
    ("must-block: UNKNOWN exhausted spend is could not tell", case_verdict_unknown_exhausted_spend_is_could_not_tell),
    ("must-allow: regressions sit beside the verdict and contaminated runs are excluded", case_verdict_keeps_regressions_beside_it_and_excludes_contaminated),
    ("must-block: total cost is UNKNOWN when any run is UNKNOWN", case_report_total_cost_is_unknown_when_any_run_is_unknown),
    ("must-allow: the real method files exist and parse", case_the_real_method_files_exist_and_parse),
    ("must-allow: every real task loads", case_every_real_task_loads),
    ("must-allow: the report command runs on a results file", case_cli_report_runs_on_a_results_file),
    ("must-block: validate needs --task or --all", case_cli_refuses_without_a_task_selection),
    ("must-allow: the shim and the canary are executable in git and the image makes the shim executable", case_the_shim_and_canary_are_executable_in_git_and_the_image),
    ("must-block: the canary runs under the scored isolation settings, no seccomp or apparmor relaxation", case_the_canary_runs_under_the_scored_isolation_settings),
    ("must-block: a malformed task.json is a refusal, not a traceback", case_load_refuses_a_malformed_task_with_a_refusal_not_a_traceback),
    ("must-block: a non-object results line is refused, not dropped (blank lines are allowed)", case_a_non_object_results_line_is_refused_not_dropped),
    ("must-block: a missing or malformed proxy log is a contamination reason", case_an_unreadable_proxy_log_is_a_contamination_reason),
    ("must-allow: an empty proxy log is a clean audit", case_an_empty_proxy_log_is_a_clean_audit),
    ("must-block: a rerun after an unscorable attempt is budget-checked first", case_a_rerun_after_an_unscorable_attempt_is_budget_checked_first),
    ("must-allow: a rerun within budget still happens", case_a_rerun_within_budget_still_happens),
    ("must-block: a Codex turn without usage fields makes usage UNKNOWN", case_codex_turn_without_usage_fields_makes_usage_unknown),
    ("must-block: a Codex session with no completed turn makes usage UNKNOWN", case_codex_session_with_no_completed_turn_makes_usage_unknown),
    ("must-block: a grading run that crashes after PASSED lines is MISSING (exit 0 and 1 still grade)", case_a_grading_run_that_crashes_after_printing_passed_lines_is_missing),
    ("must-allow: compact and pretty JSON findings arrays both parse as findings", case_a_compact_json_findings_array_parses_as_findings),
    ("must-block: grading runs in a no-network container with only the copy mounted", case_grading_runs_in_a_no_network_container_with_only_the_copy_mounted),
    ("must-block: grading goes through docker, never the host python", case_grading_goes_through_docker_and_not_the_host_python),
    ("must-allow: the arm and grading containers share the isolation options", case_the_arm_and_grading_share_the_isolation_options),
    ("must-block: the overlay does not write through a symlink the arm planted", case_overlay_does_not_write_through_a_symlink_the_arm_planted),
    ("must-allow: the overlay replaces a symlinked directory on the path and writes inside the copy", case_overlay_replaces_a_symlinked_directory_on_the_path),
    ("must-block: a grading path that leaves the repository does not load", case_load_refuses_a_grading_path_that_leaves_the_repository),
    ("must-block: a FIFO where a transcript or events file belongs is UNKNOWN or a reason, not a hang", case_a_fifo_where_a_transcript_or_events_file_belongs_is_unknown_not_a_hang),
    ("must-block: a canary for another image does not open the run gate (the current image's does)", case_a_canary_for_another_image_does_not_open_the_gate),
    ("must-block: the canary mirrors the arm isolation options, has no network and checks the interfaces", case_the_canary_mirrors_the_arm_isolation_options_and_probes_the_gateway),
    ("must-allow: a -qq run with no counts line still reads its summary", case_a_qq_run_with_no_counts_line_still_reads_its_summary),
    ("must-block: a printed PASSED line cannot override a real failure (only pytest's own summary counts)", case_a_printed_passed_line_cannot_override_a_real_failure),
    ("must-block: a grading run that hangs after its summary is unscored infra, never MISSING tests", case_a_grading_run_that_hangs_after_its_summary_is_missing),
    ("must-block: an arm-edited pytest config (pytest.ini, conftest, sitecustomize) is restored for grading", case_an_arm_edited_pytest_config_is_restored_for_grading),
    ("must-block: a Claude CLI session without a transcript makes cost UNKNOWN", case_a_claude_cli_session_without_a_transcript_makes_cost_unknown),
    ("must-block: a Codex session no events file names makes usage UNKNOWN", case_a_codex_session_no_events_file_names_makes_usage_unknown),
    ("must-block: a failed docker kill after a timeout stops the run before grading", case_a_failed_docker_kill_after_a_timeout_stops_the_run),
    ("must-block: a canary goes stale when the proxy allowlist changes (a fresh one opens the gate)", case_a_canary_goes_stale_when_the_proxy_allowlist_changes),
    ("must-block: the canary script demands the three host paths and records the fingerprint", case_the_canary_script_demands_the_three_host_paths_and_records_the_fingerprint),
    ("must-block: the budget flags refuse NaN, infinity and non-positive amounts", case_the_budget_flags_refuse_nan_infinity_and_non_positive_amounts),
    ("must-block: a second run on one results file is refused while the first holds it", case_a_second_run_on_one_results_file_is_refused),
    ("must-allow: the T-0107 task names its reference PR", case_the_t_0107_task_names_its_reference_pr),
    ("must-block: a malformed or non-finite results row spends UNKNOWN, not zero (valid rows still count)", case_a_malformed_or_non_finite_results_row_spends_unknown_not_zero),
    ("must-block: a CLI error result is unscorable whatever its message", case_a_cli_error_result_is_unscorable_whatever_its_message),
    ("must-block: a completed Codex review with no usage files is UNKNOWN (refunded and non-Codex rounds are not)", case_a_completed_codex_review_with_no_usage_files_is_unknown),
    ("must-block: the canary fails when its proxy log does not parse", case_the_canary_fails_when_its_proxy_log_does_not_parse),
    ("must-block: an indeterminate container state after a failed kill stops the run (a container that is gone does not)", case_an_indeterminate_container_state_after_a_failed_kill_stops_the_run),
    ("must-block: proxy traffic to OpenAI with no Codex files makes usage UNKNOWN (none seen, or a denied host, is zero)", case_proxy_traffic_to_openai_with_no_codex_files_makes_usage_unknown),
    ("must-block: the canary script refuses host paths that do not exist", case_the_canary_script_refuses_host_paths_that_do_not_exist),
    ("must-block: a file where the base has a directory is a refusal, not a traceback", case_a_file_where_the_base_has_a_directory_is_a_refusal_not_a_traceback),
    ("must-block: a grading container that exits 125/126/127 or is missing is infra, not MISSING tests", case_a_grading_container_that_fails_to_run_is_infra_not_missing_tests),
    ("must-block: a docker rm that hangs after a grading timeout does not hang the run", case_a_docker_rm_that_hangs_after_a_grading_timeout_does_not_hang_the_run),
    ("must-block: a grading infra failure is an unscored infra row with its cost and is not rerun", case_a_grading_infra_failure_is_an_unscored_infra_row_with_its_cost_and_no_rerun),
    ("must-block: a grading exception still writes a row with the paid cost", case_a_grading_exception_still_writes_a_row_with_the_paid_cost),
    ("must-allow: a scored run still grades through the same wrapper", case_a_scored_run_still_grades_through_the_same_wrapper),
    ("must-block: an infra or error row makes its bucket could not tell and is named", case_an_infra_or_error_row_makes_its_bucket_could_not_tell_and_is_named),
    ("must-block: a crew run that hits the resume cap is graded and marked in the row and the report", case_a_crew_run_that_hits_the_resume_cap_is_graded_and_marked),
    ("must-allow: a run that stops on its own is not marked as capped", case_a_run_that_stops_on_its_own_is_not_marked_as_capped),
    ("must-block: a CLI that exits nonzero with ok JSON is unscorable", case_a_cli_that_exits_nonzero_with_ok_json_is_unscorable),
    ("must-block: CLI JSON without a session id is unscorable", case_a_cli_json_without_a_session_id_is_unscorable),
    ("must-block: a completed Codex turn without usage makes usage UNKNOWN", case_a_completed_codex_turn_without_usage_makes_usage_unknown),
    ("must-block: a bare reference PR number is flagged; a longer number or entity is not", case_a_bare_reference_pr_number_is_flagged_but_a_longer_number_is_not),
    ("must-block: hidden-test lines spread over separate files do not flag a run (three in one file do)", case_hidden_test_lines_spread_over_separate_files_do_not_flag_a_run),
    ("must-block: the Claude auth copy is an allowlist of OAuth fields", case_the_claude_auth_copy_is_an_allowlist_of_oauth_fields),
    ("must-block: removePaths deletes from the run repo and refuses an escape", case_remove_paths_deletes_from_the_run_repo_and_refuses_an_escape),
    ("must-block: removePaths refuses a prefix sibling, a symlink escape and empty, dot or backslash entries", case_remove_paths_refuses_a_prefix_sibling_a_symlink_escape_and_bad_entries),
    ("must-allow: removePaths removes an in-repo symlink without following it", case_remove_paths_removes_a_symlink_inside_the_repo_without_following_it),
)

# pylint: enable=line-too-long


def main() -> int:
    if os.name == "nt":
        print("  NOT RUN  crew-outcome-eval: the stubs are POSIX executables; not a pass")
        return 0
    passed = failed = 0
    stub_dir = tempfile.mkdtemp(prefix="crew-outcome-stub.")
    stub = os.path.join(stub_dir, "docker")
    write(stub, DOCKER_STUB.replace("#!PYTHON", "#!" + sys.executable), EXEC)
    os.environ["CREW_OUTCOME_DOCKER"] = stub
    for name, case in CASES:
        with tempfile.TemporaryDirectory(prefix="crew-outcome-suite.") as tmp:
            try:
                ok, detail = case(tmp)
            except Exception as exc:  # noqa: BLE001 - a case that raises is a failed case, reported; pylint: disable=broad-exception-caught
                ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}\n       got {detail}")
    shutil.rmtree(stub_dir, ignore_errors=True)
    shutil.rmtree(os.path.join(REPO, "scripts", "__pycache__"), ignore_errors=True)
    print(f"\ncrew-outcome-eval: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
