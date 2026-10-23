#!/usr/bin/env python3
"""Outcome eval harness for crew (L-0728): real tasks replayed from this repo's
history, each run two ways (crew, and plain Claude Code plus /code-review), in a
container, and graded outside it.

    crew-outcome-eval.py validate [--task NAME | --all]
    crew-outcome-eval.py run --results FILE --runs-dir DIR (--task NAME | --all) [--arm crew|baseline]
    crew-outcome-eval.py report --results FILE

The method, the arm protocols and the verdict rule are frozen in
evals/crew-outcome/README.md and evals/crew-outcome/arms/*.json. Billed runs are
local only (no CI secret): CI runs scripts/_test/crew-outcome-eval.py, which
uses stub `claude`, `codex` and container-runner executables and tmp homes.

Isolation per run: a new repository made by `git init` from the task base's tree
(one commit, so the reference commit is not reachable), fresh HOME,
CLAUDE_CONFIG_DIR and CODEX_HOME holding only auth files (refresh tokens
removed: a run can never rotate the owner's login), and the arm process inside a
container whose only mounts are that run's repo and homes, behind an
allowlisting proxy. Grading happens outside the container.

An UNKNOWN cost or usage is its own value: it propagates to the run, the task
and the verdict ("could not tell") and is never read as 0 (GEN-01).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import math
import json
import os
import re
import shutil
import socket
import statistics
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
EVAL_DIR = os.path.join(REPO, "evals", "crew-outcome")
sys.path.insert(0, os.path.join(REPO, "plugin", "crew", "hooks", "scripts"))
import crew_metrics  # noqa: E402  pylint: disable=wrong-import-position

UNKNOWN = "UNKNOWN"
BUCKETS = ("S", "M", "L")
ARMS = ("crew", "baseline")
CANARY_PASS = "canary: PASS"
IMAGE = "crew-outcome-eval:1"
CLAUDE_BIN = "/usr/local/bin/claude"
PLUGIN_IN_CONTAINER = "/run/home/plugins/crew"
# Codex syncs its plugin catalogue from github.com at startup; with these off it
# reaches only the model API, so a refused github.com in the proxy log means the
# agent, not Codex, went there (spike 2026-10-19: github.com, api.github.com and
# files.openai.com were refused at the moment Codex started).
CODEX_CONFIG = ("[features]\nplugins = false\nremote_plugin = false\napps = false\n"
                "plugin_sharing = false\ndaemon_auto_start = false\n")
TASK_KEYS = ("name", "ticket", "base", "reference", "bucket", "referenceLines", "statementFile",
             "defects", "regressionInventory", "gradingFiles", "testCommand")
ARM_KEYS = ("arm", "author", "reviewer", "wallClockMinutes", "cli", "prompts")
ARM_EXTRA_KEYS = {"crew": ("crewConfig", "assignment"), "baseline": ("reviewParse",)}
TEST_TIMEOUT_SECONDS = 120
CLAUDE_OAUTH_KEEP = ("accessToken", "expiresAt", "scopes", "subscriptionType", "rateLimitTier")
# `docker kill` / `rm` / `inspect` after a timeout get a bound of their own: a cleanup that hangs
# must not hang the evaluation (L-0851).
CLEANUP_TIMEOUT_SECONDS = 30
GIT_TIMEOUT_SECONDS = 300
# `docker run` itself failing (125), the command not invokable (126) or not found (127) is the
# container, not the code under test.
DOCKER_INFRA_EXITS = (125, 126, 127)
PYTEST_GRADABLE_EXITS = (0, 1)
RESULT_WORDS = ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS")
DEFAULT_MAX_COST_USD = 150.0
DEFAULT_FIRST_RUN_ESTIMATE_USD = 25.0
CONTAINER_PROXY = "http://127.0.0.1:3128"
EVAL_RUN = "/opt/eval-shim/eval-run"
MIN_HIDDEN_LINE = 60
HIDDEN_LINES_TO_FLAG = 3
RUN_UID = "1000"
# Every container the harness starts (an arm, or grading) gets these and nothing more.
ISOLATION_OPTIONS = ("--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "1024",
                     "--memory", "6g")
MAX_ARM_FILE_BYTES = 64 * 1024 * 1024
GIT_IDENTITY = ("-c", "user.name=crew-outcome-eval", "-c", "user.email=eval@invalid")

# Codex list prices, USD per million tokens, per model. A model with no row makes
# the Codex cost UNKNOWN (U9). Rows are added only from the vendor page, with the
# date and URL they were read on.
# gpt-6-sol, Standard tier, short context (up to 272K input tokens per call), read 2026-10-23 from
# https://developers.openai.com/api/docs/pricing (the row: $2.00 input, $0.20 cached input, $10.00 output).
# Over 272K input tokens in one call the page charges 4.00 / 0.40 / 15.00. Codex reports usage per turn, not
# per call, so a call over 272K cannot be seen: the cost here is a LOWER BOUND at the short-context rate (README).
CODEX_PRICES_AS_OF = "2026-10-23"
CODEX_PRICES = {"gpt-6-sol": {"input": 2.00, "cachedInput": 0.20, "output": 10.00}}


class EvalError(Exception):
    """A refusal or a precondition that failed; the message is the whole reason."""


def fail(message):
    raise EvalError(message)


class GradingInfra(Exception):
    """Grading could not be carried out (container failed to start, timed out, or docker is
    missing). It says nothing about the code under test, so it is never a defect and never
    MISSING tests: the run is recorded unscored (`runStatus: infra`) with its cost."""


def bounded(argv):
    """(returncode, stdout, stderr) of a cleanup command, or None when it did not answer in
    CLEANUP_TIMEOUT_SECONDS."""
    try:
        out = subprocess.run(argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
                             timeout=CLEANUP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None
    return out.returncode, out.stdout, out.stderr


def which(name):
    """A tool's absolute path, or a refusal: never a bare name (GEN-08)."""
    override = os.environ.get("CREW_OUTCOME_" + name.upper())
    path = override if override and os.path.isfile(override) else shutil.which(name)
    if not path:
        fail(f"{name} not found on PATH (set CREW_OUTCOME_{name.upper()} to its absolute path)")
    return os.path.abspath(path)


def open_arm_file(path):
    """Open a file the arm could have written, for reading. A FIFO or device would
    hang or mislead the host and a huge file would be read whole, so anything that
    is not a regular file under MAX_ARM_FILE_BYTES is an OSError (callers turn that
    into UNKNOWN or a contamination reason, never into a clean reading)."""
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARM_FILE_BYTES:
        raise OSError(f"{path}: not a regular file of at most {MAX_ARM_FILE_BYTES} bytes")
    return open(path, encoding="utf-8", errors="replace")  # noqa: SIM115 - returned to a with-block


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        fail(f"{path}: cannot read as JSON: {exc}")
    return None


def git(*args, cwd=None, check=True, text=True, env=None):
    try:
        out = subprocess.run([which("git"), *args], cwd=cwd, capture_output=True, text=text,
                             check=False, stdin=subprocess.DEVNULL, env=env, timeout=GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        fail(f"git {' '.join(args[:3])} gave no answer in {GIT_TIMEOUT_SECONDS}s")
    if check and out.returncode != 0:
        detail = out.stderr.strip() if text else out.stderr.decode("utf-8", "replace").strip()
        fail(f"git {' '.join(args[:3])} failed ({out.returncode}): {detail}")
    return out


# --------------------------------------------------------------------------
# tasks

def load_task(task_dir):
    """The parsed task.json, checked for shape; `dir` is added."""
    task = read_json(os.path.join(task_dir, "task.json"))
    if not isinstance(task, dict):
        fail(f"{task_dir}/task.json is not an object")
    missing = [k for k in TASK_KEYS if k not in task]
    if missing:
        fail(f"{task_dir}/task.json lacks: {', '.join(missing)}")
    if task["bucket"] not in BUCKETS:
        fail(f"{task['name']}: bucket {task['bucket']!r} is not one of S, M, L")
    if not isinstance(task["name"], str) or not task["name"]:
        fail(f"{task_dir}/task.json: name must be a non-empty string")
    for key in ("ticket", "base", "reference", "statementFile"):
        if not isinstance(task[key], str) or not task[key]:
            fail(f"{task['name']}: {key} must be a non-empty string")
    if isinstance(task["referenceLines"], bool) or not isinstance(task["referenceLines"], int):
        fail(f"{task['name']}: referenceLines must be an integer")
    if not isinstance(task["defects"], dict) or not task["defects"]:
        fail(f"{task['name']}: defects must be a non-empty object")
    seen = {}
    for defect, ids in task["defects"].items():
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
            fail(f"{task['name']}: defect {defect!r} must list test ids as non-empty strings")
        for test_id in ids:
            if test_id in seen:
                fail(f"{task['name']}: test {test_id} is in defects {seen[test_id]!r} and {defect!r} "
                     "(defects must not overlap)")
            seen[test_id] = defect
    if not isinstance(task["testCommand"], list) or not all(isinstance(a, str) for a in task["testCommand"]):
        fail(f"{task['name']}: testCommand must be an argv list")
    for key in ("regressionInventory", "gradingFiles"):
        if not isinstance(task[key], list) or not all(isinstance(i, str) and i for i in task[key]):
            fail(f"{task['name']}: {key} must be a list of non-empty strings")
    for rel in task["gradingFiles"] + [i.split("::", 1)[0] for i in task["regressionInventory"]]:
        if os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
            fail(f"{task['name']}: {rel!r} must be a path inside the repository")
    for rel in task["gradingFiles"]:
        if not os.path.isfile(frozen_path(task_dir, rel)):
            fail(f"{task['name']}: grading file {rel} has no frozen copy ({rel}.frozen) under grading/")
    if not os.path.isfile(os.path.join(task_dir, task["statementFile"])):
        fail(f"{task['name']}: statement file {task['statementFile']} is missing")
    task["dir"] = task_dir
    return task


def task_dirs(tasks_root):
    try:
        names = sorted(os.listdir(tasks_root))
    except OSError as exc:
        fail(f"{tasks_root}: cannot list tasks: {exc}")
    return [os.path.join(tasks_root, n) for n in names if os.path.isfile(os.path.join(tasks_root, n, "task.json"))]


def frozen_path(task_dir, rel):
    """Where a grading file is stored: `grading/<rel>.frozen`. The suffix keeps
    the repo's linters, test collectors and CI selection from treating a frozen
    hidden test as a test of this repository."""
    return os.path.join(task_dir, "grading", rel + ".frozen")


def hidden_ids(task):
    return [test_id for ids in task["defects"].values() for test_id in ids]


def load_arm(path):
    arm = read_json(path)
    if not isinstance(arm, dict):
        fail(f"{path} is not an object")
    missing = [k for k in ARM_KEYS + ARM_EXTRA_KEYS.get(arm.get("arm"), ()) if k not in arm]
    if missing:
        fail(f"{path} lacks: {', '.join(missing)}")
    minutes = arm["wallClockMinutes"]
    if not isinstance(minutes, dict) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0
                                            for v in minutes.values()):
        fail(f"{path}: wallClockMinutes must map S, M, L to positive numbers")
    if set(minutes) != set(BUCKETS):
        fail(f"{path}: wallClockMinutes needs exactly S, M, L")
    return arm


def check_method(eval_dir):
    """The frozen method files exist and parse (spec Acceptance 9)."""
    if not os.path.isfile(os.path.join(eval_dir, "README.md")):
        fail(f"{eval_dir}/README.md is missing")
    return {name: load_arm(os.path.join(eval_dir, "arms", name + ".json")) for name in ARMS}


# --------------------------------------------------------------------------
# repositories and grading

def export_tree(source_repo, sha, dest):
    """`git archive <sha>` of source_repo extracted into dest."""
    os.makedirs(dest, exist_ok=True)
    out = git("archive", "--format=tar", sha, cwd=source_repo, text=False)
    with tarfile.open(fileobj=__import__("io").BytesIO(out.stdout)) as tar:
        tar.extractall(dest, filter="data")


def init_repo(dest):
    """A fresh one-commit repository of whatever is in dest."""
    git("init", "-q", "-b", "main", cwd=dest)
    git("add", "-A", cwd=dest)
    git(*GIT_IDENTITY, "commit", "-q", "-m", "base", cwd=dest)


def reference_reachable(repo, sha):
    return git("cat-file", "-e", sha + "^{commit}", cwd=repo, check=False).returncode == 0


def place(repo, rel, source):
    """Copy `source` to repo/rel without following any symlink the arm planted on
    the way: a link on the path (or at the destination) is removed first, so the
    write lands inside the copy."""
    here = repo
    parts = rel.replace("\\", "/").split("/")
    for part in parts[:-1]:
        here = os.path.join(here, part)
        if os.path.islink(here):
            os.unlink(here)
        try:
            os.makedirs(here, exist_ok=True)
        except FileExistsError:
            fail(f"grading: {rel} needs a directory at {part!r} but the run repo has a file there")
    dest = os.path.join(here, parts[-1])
    if os.path.islink(dest):
        os.unlink(dest)
    shutil.copyfile(source, dest)


TEST_CONFIG_NAMES = ("conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml", "sitecustomize.py",
                     "usercustomize.py", ".coveragerc")


def restore_test_config(repo, base_tree):
    """Make every pytest-affecting file in `repo` the base tree's: an arm-edited or
    arm-added conftest.py, pytest.ini, tox.ini, setup.cfg, pyproject.toml (addopts,
    plugins, rootdir), sitecustomize or .pth is removed and the base version put
    back, so the frozen tests run in the environment the task was validated in."""
    for here, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            if name in TEST_CONFIG_NAMES or name.endswith(".pth"):
                os.unlink(os.path.join(here, name))
    for here, dirs, names in os.walk(base_tree):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            if name in TEST_CONFIG_NAMES or name.endswith(".pth"):
                src = os.path.join(here, name)
                place(repo, os.path.relpath(src, base_tree), src)


def overlay(task, repo, base_tree, hidden):
    """Put the frozen grading set into `repo`. `hidden` False is the regression
    view: the regression inventory's test files come from the base tree (a
    deleted visible test is restored) and are NOT overlaid by the reference's
    version, so a hidden test file that imports something the arm did not write
    cannot turn a visible test red; other grading files (conftest.py, fixtures)
    are the frozen ones. `hidden` True is the full grading set."""
    keep = {test_id.split("::", 1)[0] for test_id in task["regressionInventory"]}
    if os.path.abspath(base_tree) != os.path.abspath(repo):
        restore_test_config(repo, base_tree)
    if not hidden and os.path.abspath(base_tree) != os.path.abspath(repo):
        for rel in keep:
            src = os.path.join(base_tree, rel)
            if os.path.isfile(src):
                place(repo, rel, src)
    for rel in task["gradingFiles"]:
        if not hidden and rel in keep:
            continue
        place(repo, rel, frozen_path(task["dir"], rel))


def grade_docker_argv(docker, name, user, repo, command):
    """The `docker run` that grades one copy of a run repo. The copy was written by
    the arm, so its code runs here and not on the host: no network, the same
    capability, user and resource limits as an arm, and the copy as the only mount."""
    uid, gid = user
    return [docker, "run", "--rm", "--name", name, "--network", "none", "--user", f"{uid}:{gid}",
            *ISOLATION_OPTIONS, "-v", f"{repo}:/run/repo", "-w", "/run/repo",
            "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1", IMAGE, *command]


CHOWN_TIMEOUT_SECONDS = 300


def chown_tree(uid, gid, *paths):
    """None when the trees now belong to uid:gid, else why not (failed or stalled)."""
    try:
        owned = subprocess.run(["/bin/chown", "-R", f"{uid}:{gid}", *paths], check=False, capture_output=True,
                               text=True, stdin=subprocess.DEVNULL, timeout=CHOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return f"gave no answer in {CHOWN_TIMEOUT_SECONDS}s"
    if owned.returncode != 0:
        return f"exit {owned.returncode}: {(owned.stderr or '').strip()[:200]}"
    return None


def run_tests(task, repo, ids, docker=None, sweep=()):
    """{test id: status} for the expected `ids`, by `-rA` lines; an id with no
    line (not collected, deleted, crashed run) is MISSING. Only PASSED passes.
    The test command runs in the eval image, never on the host."""
    docker = docker or which("docker")
    uid, gid, chown = container_user()
    if chown:
        problem = chown_tree(uid, gid, repo)
        if problem:
            # the container could not read the copy: that is the harness, not the code under test
            raise GradingInfra(f"chown of the grading copy failed ({problem})")
    name = f"crew-outcome-grade-{os.getpid()}-{uuid.uuid4().hex[:10]}"
    argv = grade_docker_argv(docker, name, (uid, gid), repo, task["testCommand"])
    try:
        out = subprocess.run(argv, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
                             timeout=TEST_TIMEOUT_SECONDS)
        if out.returncode in DOCKER_INFRA_EXITS:
            raise GradingInfra(f"grading container exited {out.returncode}: {(out.stderr or '').strip()[:200]}")
        text = out.stdout
        if out.returncode not in PYTEST_GRADABLE_EXITS:
            # pytest exits 0 (all passed) or 1 (some failed) for a run that finished; 2 (interrupted),
            # 3 (internal error), 4 (usage), 5 (nothing collected) or a signal is a run that cannot be
            # trusted even if it printed PASSED lines first (GEN-01: could not tell is not clean).
            text = ""
    except subprocess.TimeoutExpired as exc:
        removed = bounded([docker, "rm", "-f", name])
        raise GradingInfra(f"grading container timed out after {TEST_TIMEOUT_SECONDS}s"
                           + ("" if removed is not None else f" and docker rm -f gave no answer in "
                              f"{CLEANUP_TIMEOUT_SECONDS}s")) from exc
    except OSError as exc:
        raise GradingInfra(f"grading container could not be started: {exc}") from exc
    status = {}
    lines = summary_lines(text)
    for test_id in ids:
        status[test_id] = "MISSING"
        for line in lines:
            word, _, rest = line.partition(" ")
            if word in ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS") and (
                    rest == test_id or rest.startswith(test_id + " - ")):
                status[test_id] = word
                break
    # every other result in a hidden-only test file is read too: a hidden test nobody grouped is
    # still a hidden test
    for line in lines:
        word, _, rest = line.partition(" ")
        found = rest.split(" - ", 1)[0]
        if word in RESULT_WORDS and found not in status and found.split("::", 1)[0] in sweep:
            status[found] = word
    return status


def summary_lines(text):
    """The lines of pytest's `short test summary info` section and nothing else: from
    the LAST header to the first line that is not a result line (the counts line, which
    `-q` prints bare and `-qq` omits) or the end of output. Output the code under test prints
    (captured stdout, a plugin, an atexit hook) sits before the header or after the
    counts and is never read as a result. No header is no result at all, and a crash
    or hang is caught by the exit-code allowlist and the timeout, not here. Residual, stated in the README: the
    code under test runs inside pytest's own process and could forge the whole output;
    this closes the stdout-echo vector, not a determined forger."""
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    header = None
    for number, line in enumerate(lines):
        if re.fullmatch(r"=+ short test summary info =+", line):
            header = number
    if header is None:
        return []
    results = []
    for line in lines[header + 1:]:
        if line.partition(" ")[0] in RESULT_WORDS:
            results.append(line)
            continue
        return results if line.strip() else []
    return results


def graded_status(task, repo, base_tree, tmp, docker=None):
    """({regression id: status}, {hidden id: status}) from two copies of `repo`:
    the regression view and the full grading set (see `overlay`)."""
    out = []
    keep = {test_id.split("::", 1)[0] for test_id in task["regressionInventory"]}
    for hidden, ids in ((False, task["regressionInventory"]), (True, hidden_ids(task))):
        copy = os.path.join(tmp, "hidden" if hidden else "regression")
        shutil.copytree(repo, copy, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        overlay(task, copy, base_tree, hidden)
        sweep = {rel for rel in task["gradingFiles"] if rel not in keep and os.path.basename(rel).startswith("test_")}
        out.append(run_tests(task, copy, ids, docker, sweep if hidden else ()))
    return out[0], out[1]


def grade(task, repo, source_repo, docker=None):
    """Grade a run repo on copies of it, in a fresh no-network container (the arm's
    code never runs on the host): every expected id must report PASSED."""
    with tempfile.TemporaryDirectory(prefix="crew-outcome-grade.") as tmp:
        base_tree = os.path.join(tmp, "base")
        export_tree(source_repo, task["base"], base_tree)
        regression, hidden = graded_status(task, repo, base_tree, tmp, docker)
    escaped = [name for name, ids in task["defects"].items() if any(hidden[i] != "PASSED" for i in ids)]
    grouped = set(hidden_ids(task))
    if any(status != "PASSED" for test_id, status in hidden.items() if test_id not in grouped):
        escaped.append("ungrouped-hidden-tests")
    failed = [i for i in task["regressionInventory"] if regression[i] != "PASSED"]
    return {"escapedDefects": len(escaped), "defectsTotal": len(task["defects"]),
            "escapedDefectNames": escaped, "regressionTestsFailed": len(failed)}


def validate_task(task, source_repo, docker=None):
    """Refuse a task whose hidden tests pass at base or fail at reference, whose
    regression inventory does not pass at base or at reference, or whose base or
    reference sha is not resolvable in the source repository."""
    for label in ("reference", "base"):
        if git("cat-file", "-e", task[label] + "^{commit}", cwd=source_repo, check=False).returncode != 0:
            return [f"{task['name']}: {label} {task[label]} is not a commit in {source_repo}"]
    problems = []
    with tempfile.TemporaryDirectory(prefix="crew-outcome-validate.") as tmp:
        for label in ("base", "reference"):
            tree = os.path.join(tmp, label)
            export_tree(source_repo, task[label], tree)
            init_repo(tree)
            scratch = os.path.join(tmp, label + "-scratch")
            os.makedirs(scratch)
            regression, hidden = graded_status(task, tree, tree, scratch, docker)
            bad = [i for i in task["regressionInventory"] if regression[i] != "PASSED"]
            if bad:
                problems.append(f"{task['name']}: regression tests do not pass at {label}: {', '.join(bad)}")
            if label == "base":
                passing = [i for i in hidden_ids(task) if hidden[i] == "PASSED"]
                if passing:
                    problems.append(f"{task['name']}: hidden tests pass at base: {', '.join(passing)}")
            else:
                bad = [i for i in hidden if hidden[i] != "PASSED"]
                if bad:
                    problems.append(f"{task['name']}: tests fail at reference: {', '.join(bad)}")
    return problems


# --------------------------------------------------------------------------
# usage and cost

def claude_usage(home, sessions=()):
    """(tokens, cost, models) over every Claude Code transcript under the run's
    own CLAUDE_CONFIG_DIR, subagent files included, each message once. Cost is
    UNKNOWN when any session is missing, unparseable or unpriced, or when a
    subagent a transcript names has no file."""
    config = os.path.join(home, ".claude")
    projects = os.path.join(config, "projects")
    errors = []
    files = []
    try:
        slugs = sorted(os.listdir(projects))
    except OSError:
        return UNKNOWN, UNKNOWN, ["no transcripts"]
    for slug in slugs:
        # pylint: disable-next=protected-access
        files.extend(crew_metrics._session_files(os.path.join(projects, slug), errors))
    if errors or not files:
        return UNKNOWN, UNKNOWN, ["transcripts cannot be listed" if errors else "no transcripts"]
    have = {os.path.basename(path)[:-len(".jsonl")] for path, parent in files if not parent}
    absent = sorted(set(sessions) - have)
    if absent:
        return UNKNOWN, UNKNOWN, [f"no transcript for CLI session {', '.join(absent)}"]
    for path, _parent in files:
        try:
            with open_arm_file(path):
                pass
        except OSError:
            return UNKNOWN, UNKNOWN, [f"{os.path.basename(path)} is not a readable transcript"]
    messages = {}
    named_agents, have_agents = set(), set()
    for path, parent in files:
        # pylint: disable-next=protected-access
        bad, _ids, _cwds, _missing, found = crew_metrics._scan_file(path)
        if bad:
            return UNKNOWN, UNKNOWN, [f"{os.path.basename(path)} does not parse"]
        if parent:
            have_agents.add(re.sub(r"^agent-|\.jsonl$", "", os.path.basename(path)))
        named_agents |= subagent_ids(path)
        for key, (kinds, model) in found.items():
            old = messages.get(key)
            if old is None or sum(kinds) > sum(old[0]):
                messages[key] = (kinds, model)
    missing = sorted(named_agents - have_agents)
    # pylint: disable-next=protected-access
    by_model, tokens = crew_metrics._fold_kinds(messages.values())
    if missing:
        return tokens, UNKNOWN, [f"subagent transcript missing: {', '.join(missing)}"]
    cost, unpriced = crew_metrics.cost_usd(by_model)
    return tokens, cost, unpriced


def subagent_ids(path):
    """The agent ids a main transcript's tool results name."""
    found = set()
    try:
        with open_arm_file(path) as fh:
            for line in fh:
                if '"agentId"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                result = rec.get("toolUseResult") if isinstance(rec, dict) else None
                agent = result.get("agentId") if isinstance(result, dict) else None
                if isinstance(agent, str) and agent:
                    found.add(agent)
    except OSError:
        pass
    return found


def codex_usage(repo, home, model, proxy_log=None):
    """(tokens, cost): the sum of every `turn.completed` usage in the run's
    codex-events.jsonl files. UNKNOWN when a Codex session exists in the run's
    own CODEX_HOME that no events file accounts for, when an events file does
    not parse, or (cost) when the model has no price row. A run with no Codex
    call at all is zero tokens at zero cost: that is a measurement, not a gap."""
    events = []
    for here, _dirs, names in os.walk(repo):
        # review_run.py writes codex-events.jsonl for a review and probe-events.jsonl for its
        # availability probe; each is a Codex session of its own (spike: 2 sessions, 2 files).
        events.extend(os.path.join(here, n) for n in names if n in ("codex-events.jsonl", "probe-events.jsonl"))
    sessions = []
    for here, _dirs, names in os.walk(os.path.join(home, ".codex", "sessions")):
        sessions.extend(n for n in names if n.endswith(".jsonl"))
    threads = set()
    total = {"input": 0, "cachedInput": 0, "output": 0, "reasoning": 0}
    turns = 0
    for path in events:
        try:
            with open_arm_file(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if isinstance(rec, dict) and rec.get("type") == "thread.started":
                        threads.add(str(rec.get("thread_id")))
                    completed = isinstance(rec, dict) and rec.get("type") == "turn.completed"
                    usage = rec.get("usage") if completed else None
                    if completed and not isinstance(usage, dict):
                        # a finished turn that reports no usage was not measured: not a zero
                        return UNKNOWN, UNKNOWN
                    if isinstance(usage, dict):
                        turns += 1
                        for needed in ("input_tokens", "output_tokens"):
                            if isinstance(usage.get(needed), bool) or not isinstance(usage.get(needed), int):
                                return UNKNOWN, UNKNOWN
                        for optional in ("cached_input_tokens", "reasoning_output_tokens"):
                            value = usage.get(optional)
                            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                                return UNKNOWN, UNKNOWN
                        counts = [usage.get(k) or 0 for k in ("input_tokens", "cached_input_tokens",
                                                              "output_tokens", "reasoning_output_tokens")]
                        if (any(c < 0 for c in counts) or counts[1] > counts[0] or counts[3] > counts[2]):
                            return UNKNOWN, UNKNOWN
                        total["input"] += int(usage.get("input_tokens") or 0)
                        total["cachedInput"] += int(usage.get("cached_input_tokens") or 0)
                        total["output"] += int(usage.get("output_tokens") or 0)
                        total["reasoning"] += int(usage.get("reasoning_output_tokens") or 0)
        except (OSError, ValueError, TypeError):
            return UNKNOWN, UNKNOWN
    if len(sessions) > len(events):
        return UNKNOWN, UNKNOWN
    if any(not any(name[:-len(".jsonl")].endswith(thread) for thread in threads) for name in sessions):
        # a session log whose id no events file names was not measured
        return UNKNOWN, UNKNOWN
    if sessions and not turns:
        # a Codex session ran but no events file recorded a completed turn: nothing was measured
        return UNKNOWN, UNKNOWN
    if not events and not sessions and proxy_log is not None and codex_hosts_allowed(proxy_log) != 0:
        # the host-side proxy saw traffic to a Codex/OpenAI host the arm's own files do not account for
        return UNKNOWN, UNKNOWN
    if not events and not sessions and codex_review_rounds(repo) != 0:
        # a completed Codex review in the ledger with no events file and no session log: uncounted
        return UNKNOWN, UNKNOWN
    if not events:
        return total, 0.0
    return total, codex_cost(total, model)


def codex_hosts_allowed(proxy_log):
    """How many allowed CONNECTs the proxy logged to OpenAI hosts; -1 when the log
    cannot be read. The proxy is a host process the arm cannot write to, so unlike
    the arm's own files this count is not scrubbable."""
    count = 0
    try:
        with open(proxy_log, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                host = str(rec.get("host", "")) if isinstance(rec, dict) else ""
                if isinstance(rec, dict) and rec.get("decision") == "allow" and (
                        host == "api.openai.com" or host == "chatgpt.com" or host.endswith(".chatgpt.com")):
                    count += 1
    except (OSError, ValueError):
        return -1
    return count


def codex_review_rounds(repo):
    """How many non-refunded Codex review rounds the run repo's ledgers record; -1
    when a ledger cannot be read (so the caller treats it as 'cannot tell')."""
    base = os.path.join(repo, ".git", "crew", "review")
    try:
        names = [n for n in os.listdir(base) if n.endswith(".json")]
    except OSError:
        return 0
    count = 0
    for name in names:
        try:
            with open_arm_file(os.path.join(base, name)) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return -1
        rows = data.get("rounds", []) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return -1
        count += sum(1 for r in rows if isinstance(r, dict) and r.get("provider") == "codex" and not r.get("refunded"))
    return count


def codex_cost(tokens, model):
    row = CODEX_PRICES.get(model) if model else None
    if row is None:
        return UNKNOWN
    uncached = max(tokens["input"] - tokens["cachedInput"], 0)
    return round((uncached * row["input"] + tokens["cachedInput"] * row["cachedInput"]
                  + tokens["output"] * row["output"]) / 1_000_000, 6)


def add_costs(*parts):
    if any(p == UNKNOWN for p in parts):
        return UNKNOWN
    return round(sum(parts), 6)


# --------------------------------------------------------------------------
# contamination

def contamination(task, home, repo, proxy_log, arm, source_repo):
    """Evidence that a run reached the reference, as a list of reasons (empty:
    none). Only evidence counts: the reference sha, the reference PR's URL, a
    hidden test's file content in a transcript or Codex event, or a proxy-refused
    host that is not on the arm's ignore list. Text that exists in the base tree
    (README, marketplace.json) never flags a run."""
    needles = {task["reference"]: "reference sha"}
    patterns = {}
    if task.get("referencePr"):
        number = re.escape(str(task["referencePr"]))
        # whole numbers only: /pull/2730 and #2730 are not PR 273; a bare #273 counts, an HTML entity &#273; does not
        patterns["reference PR URL"] = re.compile(rf"/pull/{number}(?![0-9A-Za-z_])")
        patterns["reference PR number"] = re.compile(rf"(?<!&)#{number}(?![0-9A-Za-z_])")
    texts = []
    roots = [os.path.join(home, ".claude", "projects"), os.path.join(home, ".codex", "sessions")]
    for root in roots:
        for here, _dirs, names in os.walk(root):
            texts.extend(os.path.join(here, n) for n in names if n.endswith(".jsonl"))
    for here, _dirs, names in os.walk(repo):
        texts.extend(os.path.join(here, n) for n in names if n in ("codex-events.jsonl", "probe-events.jsonl"))
    hidden_lines = hidden_content_lines(task, source_repo)
    reasons = []
    most_hits = 0
    for path in texts:
        try:
            with open_arm_file(path) as fh:
                body = fh.read()
        except OSError:
            if "unreadable arm file" not in reasons:
                reasons.append("unreadable arm file")
            continue
        for needle, label in needles.items():
            if needle in body and label not in reasons:
                reasons.append(label)
        for label, pattern in patterns.items():
            if label not in reasons and pattern.search(body):
                reasons.append(label)
        # the threshold is three distinctive lines in ONE file: lines found in different files are not summed
        in_file = {line for line in hidden_lines if line in body or json.dumps(line)[1:-1] in body}
        most_hits = max(most_hits, len(in_file))
    if most_hits >= HIDDEN_LINES_TO_FLAG:
        reasons.append("hidden test content")
    ignore = set(arm.get("proxyIgnoreHosts", []))
    denied = proxy_denied_hosts(proxy_log)
    if denied is None:
        reasons.append("network audit unreadable")
    else:
        for host in denied:
            if host not in ignore:
                reasons.append(f"network host {host}")
    return reasons


def hidden_content_lines(task, source_repo):
    """Distinctive lines of the grading files: MIN_HIDDEN_LINE+ characters, not in
    the base version of that file and not in the task statement (a line the agent
    was given, or the base already has, can never be evidence of reference
    access; short asserts an agent writes on its own often coincide)."""
    with open(os.path.join(task["dir"], task["statementFile"]), encoding="utf-8", errors="replace") as fh:
        given = {line.strip() for line in fh}
    lines = set()
    for rel in task["gradingFiles"]:
        shown = git("show", f"{task['base']}:{rel}", cwd=source_repo, check=False)
        given |= {line.strip() for line in shown.stdout.splitlines()} if shown.returncode == 0 else set()
        try:
            with open(frozen_path(task["dir"], rel), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    stripped = line.strip()
                    if len(stripped) >= MIN_HIDDEN_LINE and stripped not in given:
                        lines.add(stripped)
        except OSError:
            continue
    return lines


def proxy_denied_hosts(proxy_log):
    """The hosts the proxy refused, or None when the log is missing or has a line
    that is not a JSON object: an unreadable network audit is not a clean one."""
    hosts = []
    try:
        with open(proxy_log, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    return None
                if not isinstance(rec, dict):
                    return None
                if rec.get("decision") == "deny":
                    hosts.append(rec.get("host") or rec.get("request") or "?")
    except OSError:
        return None
    return hosts


# --------------------------------------------------------------------------
# budget

def read_results(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    fail(f"{path}:{number}: not JSON; results are append-only full lines")
                if not isinstance(row, dict):
                    fail(f"{path}:{number}: not a JSON object; results are append-only full rows")
                if not all(isinstance(row.get(k), str) for k in ("task", "bucket", "arm", "runStatus")):
                    fail(f"{path}:{number}: task, bucket, arm and runStatus must be present strings")
                for key in ("costUsd", "ownCostUsd", "unscoredSpendUsd", "claudeCostUsd", "escapedDefects",
                            "regressionTestsFailed"):
                    value = row.get(key)
                    if key in row and value is not None and value != UNKNOWN and (
                            isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(value) or value < 0):
                        fail(f"{path}:{number}: {key} must be a non-negative number, null or {UNKNOWN}")
                rows.append(row)
    except FileNotFoundError:
        return []
    except OSError as exc:
        fail(f"{path}: cannot read: {exc}")
    return rows


def append_result(path, row):
    """One full JSON line per run, written in a single append (GEN-02)."""
    line = json.dumps(row, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


def spend_of(row):
    """What this one attempt cost: its own spend, never the carried cost of an
    earlier attempt (which `costUsd` includes), so nothing is counted twice."""
    cost = row["ownCostUsd"] if "ownCostUsd" in row else row.get("costUsd", UNKNOWN)
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        return UNKNOWN
    return float(cost)


def budget_check(rows, bucket, arm, max_cost, first_run_estimate):
    """Raise EvalError when the next run must not start. The cap is a scheduling
    threshold, not a meter: spent so far plus the projected cost of this run may
    not pass it. Projection: the highest cost observed for this bucket and arm,
    else the highest for this arm (the pilot's), else the first-run estimate.
    A run whose cost is UNKNOWN stops the batch."""
    spent = 0.0
    seen_bucket, seen_arm = [], []
    for row in rows:
        cost = spend_of(row)
        if cost == UNKNOWN:
            fail(f"stopped: a run's cost is UNKNOWN ({row.get('task')}/{row.get('arm')} attempt "
                 f"{row.get('attempt')}); fix the cause before spending more")
        spent += cost
        if row.get("arm") == arm:
            seen_arm.append(cost)
            if row.get("bucket") == bucket:
                seen_bucket.append(cost)
    projection = max(seen_bucket) if seen_bucket else max(seen_arm) if seen_arm else first_run_estimate
    if spent + projection > max_cost:
        fail(f"budget: spent {spent:.2f} + projected {projection:.2f} would pass --max-cost-usd {max_cost:.2f}")
    return spent, projection


# --------------------------------------------------------------------------
# container runner

def container_user():
    """(uid, gid, chown): a root host runs the arm as uid 1000 (Claude Code
    refuses --dangerously-skip-permissions as root) and hands the run dir over."""
    if os.geteuid() == 0:
        return RUN_UID, RUN_UID, True
    return str(os.geteuid()), str(os.getegid()), False


def arm_docker_argv(docker, run, name, user, inner):
    """The `docker run` for one arm invocation. The only mounts are this run's
    repo and home and the proxy's socket directory: the host checkout, the task
    store and earlier runs are not among them (the canary proves they are not
    visible). `--network none`: the container has a loopback and nothing else, so
    the host's own services (ssh, a docker API, a database) are not reachable;
    the only way out is `eval-run`, which forwards 127.0.0.1:3128 to the
    allowlisting proxy's unix socket."""
    uid, gid = user
    return [docker, "run", "--rm", "--name", name, "--network", "none", "--user", f"{uid}:{gid}",
            *ISOLATION_OPTIONS,
            # No seccomp or AppArmor relaxation: the image's `codex` shim runs Codex with
            # `--sandbox danger-full-access`, so this container is the only boundary.
            "-v", f"{run['repo']}:/run/repo", "-v", f"{run['home']}:/run/home",
            "-v", f"{run['proxysock']}:/run/proxy",
            "-e", "HOME=/run/home", "-e", "CLAUDE_CONFIG_DIR=/run/home/.claude",
            "-e", "CODEX_HOME=/run/home/.codex", "-e", f"HTTPS_PROXY={CONTAINER_PROXY}",
            "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", "-e", "DISABLE_AUTOUPDATER=1",
            "-e", "GIT_AUTHOR_NAME=crew-outcome-eval", "-e", "GIT_AUTHOR_EMAIL=eval@invalid",
            "-e", "GIT_COMMITTER_NAME=crew-outcome-eval", "-e", "GIT_COMMITTER_EMAIL=eval@invalid",
            "-w", "/run/repo", IMAGE, EVAL_RUN, *inner]


class Proxy:
    """The allowlisting proxy for one run: a host process listening on a unix
    socket in the run's proxysock directory (mounted into the arm container as
    /run/proxy). The container has no network at all; this socket is its only
    way out. The proxy's decisions are in <run>/proxylog/proxy.jsonl."""

    def __init__(self, run, container_dir):
        self.run, self.container_dir = run, container_dir
        self.sock = os.path.join(run["proxysock"], "proxy.sock")
        self.proc = None

    def __enter__(self):
        log = os.path.join(self.run["proxylog"], "proxy.jsonl")
        # created empty here so that a missing log later means it was removed, not that nothing happened
        with open(log, "a", encoding="utf-8"):
            pass
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(self.container_dir, "proxy.py"),
             os.path.join(self.container_dir, "proxy-allowlist.txt"), log, self.sock],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                break
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.connect(self.sock)
                return self
            except OSError:
                time.sleep(0.1)
            finally:
                probe.close()
        self.__exit__()
        return fail(f"the proxy did not start on {self.sock}")

    def __exit__(self, *_exc):
        if self.proc is not None:
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=5)
            if self.proc.poll() is None:
                self.proc.kill()
        return False


def sh(*argv):
    out = subprocess.run(list(argv), capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    if out.returncode != 0:
        fail(f"{os.path.basename(argv[0])} {' '.join(argv[1:3])} failed ({out.returncode}): {out.stderr.strip()}")
    return out.stdout


def invoke(docker, run, name, inner, timeout):
    """One arm invocation in the container. (exit code, stdout, timed_out)."""
    argv = arm_docker_argv(docker, run, name, container_user()[:2], inner)
    try:
        out = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout,
                             stdin=subprocess.DEVNULL)
        return out.returncode, out.stdout, False
    except subprocess.TimeoutExpired as exc:
        killed = bounded([docker, "kill", name])
        if killed is None or killed[0] != 0:
            bounded([docker, "rm", "-f", name])
            probe = bounded([docker, "inspect", "-f", "{{.State.Running}}", name])
            gone = probe is not None and probe[0] != 0 and "no such" in (probe[2] or "").lower()
            if not gone and (probe is None or probe[0] != 0 or probe[1].strip() == "true"):
                fail(f"container {name} timed out and could not be stopped; "
                     "not grading a run that may still be writing")
        text = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return 124, text, True


# --------------------------------------------------------------------------
# preparing a run

def strip_claude_auth(source, dest):
    """Only the OAuth access token, never the refresh token: the run cannot
    rotate the owner's login."""
    data = read_json(source)
    entry = data.get("claudeAiOauth") if isinstance(data.get("claudeAiOauth"), dict) else {}
    # An allowlist, not a copy minus one key: any other field the owner's file carries stays behind.
    oauth = {k: entry[k] for k in CLAUDE_OAUTH_KEEP if k in entry}
    if not oauth:
        fail(f"{source} has no claudeAiOauth entry")
    write_private(dest, json.dumps({"claudeAiOauth": oauth}))


def strip_codex_auth(source, dest):
    data = read_json(source)
    tokens = dict(data.get("tokens")) if isinstance(data.get("tokens"), dict) else {}
    if not tokens:
        fail(f"{source} has no tokens entry")
    # Codex treats a login with no refresh token as signed out and falls back to
    # an unauthenticated api.openai.com call (spike: 401), so a placeholder stays;
    # it is useless anywhere, and auth.openai.com is not on the proxy allowlist.
    tokens["refresh_token"] = "refresh-token-removed"
    # An allowlist, not a copy: no OPENAI_API_KEY and no other key the owner's file carries.
    # last_refresh stays: without it Codex tries to refresh the login at auth.openai.com, which
    # the proxy refuses (spike 2026-10-20). id_token stays because Codex needs it to read the
    # account (it names the account and email: accepted, README Isolation).
    kept = {k: tokens[k] for k in ("access_token", "id_token", "account_id", "refresh_token") if k in tokens}
    out = {"auth_mode": data.get("auth_mode", "chatgpt"), "tokens": kept}
    if "last_refresh" in data:
        out["last_refresh"] = data["last_refresh"]
    write_private(dest, json.dumps(out))


def write_private(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def prepare_run(task, arm, source_repo, runs_dir, attempt, crew_plugin, env=None):
    """The run directory: repo (fresh git init from the base tree), home with
    auth files only, and the arm's own settings."""
    env = os.environ if env is None else env
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    run_dir = os.path.join(os.path.abspath(runs_dir), f"{task['name']}-{arm['arm']}-a{attempt}-{stamp}-{os.getpid()}")
    run = {"dir": run_dir, "repo": os.path.join(run_dir, "repo"), "home": os.path.join(run_dir, "home"),
           "proxylog": os.path.join(run_dir, "proxylog"), "proxysock": os.path.join(run_dir, "proxysock")}
    for key in ("repo", "home", "proxylog", "proxysock"):
        os.makedirs(run[key])
    export_tree(source_repo, task["base"], run["repo"])
    init_repo(run["repo"])
    if reference_reachable(run["repo"], task["reference"]):
        fail(f"{task['name']}: the reference {task['reference']} is reachable in the run repo")
    claude_src = env.get("CLAUDE_CONFIG_DIR") or os.path.join(env.get("HOME", ""), ".claude")
    codex_src = env.get("CODEX_HOME") or os.path.join(env.get("HOME", ""), ".codex")
    strip_claude_auth(os.path.join(claude_src, ".credentials.json"),
                      os.path.join(run["home"], ".claude", ".credentials.json"))
    strip_codex_auth(os.path.join(codex_src, "auth.json"), os.path.join(run["home"], ".codex", "auth.json"))
    write_private(os.path.join(run["home"], ".codex", "config.toml"), CODEX_CONFIG)
    settings = {"permissions": {"deny": ["WebFetch", "WebSearch"]}, **arm.get("settings", {})}
    write_private(os.path.join(run["home"], ".claude", "settings.json"), json.dumps(settings))
    write_private(os.path.join(run["home"], ".claude.json"),
                  json.dumps({"hasCompletedOnboarding": True, "theme": "dark"}))
    with open(os.path.join(run["repo"], ".git", "info", "exclude"), "a", encoding="utf-8") as fh:
        fh.write("/.crew/config.json\n/.work/\n__pycache__/\n.pytest_cache/\n")
    if arm["arm"] == "crew":
        plugin_dest = os.path.join(run["home"], "plugins", "crew")
        shutil.copytree(crew_plugin, plugin_dest, ignore=shutil.ignore_patterns("__pycache__", "tests", "evals"))
        write_private(os.path.join(run["repo"], ".crew", "config.json"), json.dumps(arm["crewConfig"]))
        write_assignment(run, task, arm)
    if os.geteuid() == 0:
        problem = chown_tree(RUN_UID, RUN_UID, run["repo"], run["home"])
        if problem:
            fail(f"chown of the run directory failed ({problem}); nothing was started")
    return run


def write_assignment(run, task, arm):
    """The staging file `crew_ticket.py assign` reads (`.work/autopilot/
    assign-<n>.md`, README): the task statement verbatim as the Ask. It is the
    supported way to a ticket whose direction is already approved, with no human;
    `/crew:brainstorm` ends at a direction nobody can approve unattended
    (spike 2026-10-19: `phase=direction-approval stop=1 decision=direction`)."""
    with open(os.path.join(task["dir"], task["statementFile"]), encoding="utf-8") as fh:
        statement = fh.read().rstrip("\n")
    text = render(arm["assignment"]["template"], {"title": task["name"], "risk": arm["assignment"]["risk"],
                                                  "statement": statement})
    write_private(os.path.join(run["repo"], ".work", "autopilot", "assign-1.md"), text)


# --------------------------------------------------------------------------
# arms

def render(template, values):
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def cli_argv(arm, prompt, resume=None):
    argv = [CLAUDE_BIN, "-p", prompt, "--output-format", "json", *arm["cli"]["args"]]
    if resume:
        argv += ["--resume", resume]
    return argv


def parse_cli_json(text):
    """The CLI's final JSON object, or None. `claude -p --output-format json`
    prints one object (or a list of events whose last is the result)."""
    text = text.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, list):
        data = next((e for e in reversed(data) if isinstance(e, dict) and e.get("type") == "result"), None)
    return data if isinstance(data, dict) else None


def review_verdict(arm, text):
    """'clean', 'findings' or 'unparseable' by the arm file's parse rule."""
    rule = arm["reviewParse"]
    has_findings = bool(re.search(rule["findings"], text, re.M))
    no_findings = bool(re.search(rule["noFindings"], text, re.M))
    if has_findings and not no_findings:
        return "findings"
    if no_findings and not has_findings:
        return "clean"
    return "unparseable"


def crew_rounds(repo):
    """(cycles, incomplete) from the run repo's review ledgers."""
    cycles = incomplete = 0
    base = os.path.join(repo, ".git", "crew", "review")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return 0, 0
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open_arm_file(os.path.join(base, name)) as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            incomplete += 1
            continue
        rows = data.get("rounds", []) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            # an arm-written ledger of the wrong shape cannot be counted: incomplete, never an exception
            # that would lose the paid attempt's row
            incomplete += 1
            continue
        for row in rows:
            if not isinstance(row, dict):
                incomplete += 1
            elif row.get("verdict") in ("CLEAN", "FINDINGS"):
                cycles += 1
            elif row.get("status") != "reserved" or row.get("verdict") == "INCOMPLETE":
                incomplete += 1
            else:
                incomplete += 1
    return cycles, incomplete


def autopilot_stopped(shell, ticket):
    """True when autopilot's own `next` says `stop=1` (a person is needed, or the
    ticket is closed), False on an explicit `stop=0`, and None when the probe
    itself failed or said nothing readable: that is a harness fault, never a stop."""
    code, text = shell(f"python3 -B {PLUGIN_IN_CONTAINER}/hooks/scripts/crew_autopilot.py next --root . "
                       f"--ticket {ticket} --phases-run 0 --last-command '' --runner autopilot")
    found = re.search(r"\bstop=([01])\b", text)
    if code != 0 or not found:
        return None
    return found.group(1) == "1"


class Clock:
    """Monotonic seconds; injectable so the suite does not sleep."""

    def __call__(self):
        return time.monotonic()


def drive_arm(docker, run, task, arm, clock, holder=None):
    """Run the arm's protocol. Returns {sessions, exit, cycles, incomplete,
    cliTotalCostUsd, failure} where failure is a harness/auth/container/API
    problem (the run is then unscorable) or None."""
    limit = arm["wallClockMinutes"][task["bucket"]] * 60
    started = clock()
    with open(os.path.join(task["dir"], task["statementFile"]), encoding="utf-8") as fh:
        statement = fh.read()
    values = {"statement": statement, "ticket": task["ticket"]}
    out = holder if holder is not None else {}
    out.update({"sessions": [], "exit": 0, "cycles": 0, "incomplete": 0, "cliTotalCostUsd": 0.0, "failure": None,
                "endedBy": "stop"})
    cli_cost = {}
    kept = [0]
    session = None

    def step(prompt, resume):
        remaining = limit - (clock() - started)
        if remaining <= 0:
            return None
        name = f"crew-outcome-arm-{os.path.basename(run['dir'])}-{len(out['sessions'])}"
        code, text, timed_out = invoke(docker, run, name, cli_argv(arm, prompt, resume), remaining)
        data = parse_cli_json(text)
        out["exit"] = code
        if data is None:
            if timed_out:
                return {"timedOut": True}
            out["failure"] = f"no CLI JSON (exit {code})"
            return None
        if data.get("is_error"):
            out["failure"] = "CLI reported an error: " + str(data.get("result", ""))[:200]
            return None
        if code != 0:
            out["failure"] = f"CLI exited {code} although its JSON reports no error"
            return None
        if not isinstance(data.get("session_id"), str) or not data["session_id"]:
            out["failure"] = "CLI JSON has no session_id, so its transcript and cost cannot be checked"
            return None
        kept[0] += 1
        write_private(os.path.join(run["dir"], "cli", f"{kept[0]:02d}.json"), text)
        sid = data["session_id"]
        out["sessions"].append(sid)
        # The CLI reports `total_cost_usd` for the whole session so far, so a `--resume`
        # repeats what the invocation before it reported (spike): the last value counts.
        cost = data.get("total_cost_usd")
        cli_cost[sid] = UNKNOWN if not isinstance(cost, (int, float)) else cost
        out["cliTotalCostUsd"] = UNKNOWN if UNKNOWN in cli_cost.values() else round(sum(cli_cost.values()), 6)
        return data

    def shell(command):
        remaining = max(limit - (clock() - started), 1)
        name = f"crew-outcome-sh-{os.path.basename(run['dir'])}-{int(clock())}"
        code, text, _timed = invoke(docker, run, name, ["/bin/bash", "-c", command], min(remaining, 600))
        return code, text

    if arm["arm"] == "crew":
        code, text = shell(f"python3 -B {PLUGIN_IN_CONTAINER}/hooks/scripts/crew_ticket.py assign "
                           "--root . --direction-file .work/autopilot/assign-1.md")
        found = re.search(r"^ticket=(\S+)", text, re.M)
        if code != 0 or not found:
            out["failure"] = f"crew_ticket.py assign failed (exit {code}): {text.strip()[:200]}"
            return out
        values["ticket"] = found.group(1)
        data = step(render(arm["prompts"]["start"], values), None)
        resumes = 0
        while data and not data.get("timedOut") and resumes < arm["cli"].get("maxResumes", 0):
            stopped = autopilot_stopped(shell, values["ticket"])
            if stopped is None:
                out["failure"] = "autopilot status probe failed or was unreadable"
                return out
            if stopped:
                break
            resumes += 1
            data = step(render(arm["prompts"]["resume"], values), data.get("session_id"))
        else:
            stopped = autopilot_stopped(shell, values["ticket"]) if data and not data.get("timedOut") else True
            if stopped is None:
                out["failure"] = "autopilot status probe failed or was unreadable"
                return out
            if not stopped:
                # Graded as it stands, like a wall-clock stop (spec U1), and said so in the row: the harness
                # cap ended the arm, autopilot did not.
                out["endedBy"] = "resume-cap"
        if data and data.get("timedOut"):
            out["endedBy"] = "wall-clock"
        out["cycles"], out["incomplete"] = crew_rounds(run["repo"])
    else:
        data = step(render(arm["prompts"]["implement"], values), None)
        session = data.get("session_id") if data and not data.get("timedOut") else None
        cycles = incomplete = 0
        attempts = 0
        while data and not data.get("timedOut") and cycles < arm["cli"].get("maxCycles", 3):
            review = step(render(arm["prompts"]["review"], values), None)
            if review is None and out["failure"]:
                # an errored review is an incomplete attempt, retried once like an unparseable one
                incomplete += 1
                attempts += 1
                if attempts > 1:
                    break
                out["failure"] = None
                continue
            if not review or review.get("timedOut"):
                break
            verdict = review_verdict(arm, str(review.get("result", "")))
            if verdict == "unparseable":
                incomplete += 1
                attempts += 1
                if attempts > 1:
                    break
                continue
            attempts = 0
            cycles += 1
            if verdict == "clean":
                break
            findings = str(review.get("result", ""))
            data = step(render(arm["prompts"]["fix"], {**values, "findings": findings}), session)
        out["cycles"], out["incomplete"] = cycles, incomplete
    return out


# --------------------------------------------------------------------------
# one run

def run_once(ctx, task, arm, attempt, carried_cost=0.0):
    """One attempt: prepare, run, collect, grade. Returns the results row."""
    run = prepare_run(task, arm, ctx["source_repo"], ctx["runs_dir"], attempt, ctx["crew_plugin"], ctx.get("env"))
    clock = ctx.get("clock") or Clock()
    started = clock()
    holder = {"sessions": [], "exit": 0, "cycles": 0, "incomplete": 0, "cliTotalCostUsd": UNKNOWN,
              "failure": None, "endedBy": "stop"}
    try:
        with Proxy(run, ctx["container_dir"]):
            driven = drive_arm(ctx["docker"], run, task, arm, clock, holder)
    except Exception as exc:  # noqa: BLE001 - the invocations before it were paid for: the row is still written; pylint: disable=broad-exception-caught
        driven = holder
        driven["failure"] = f"arm driver raised {type(exc).__name__}: {exc}"
        driven["cliTotalCostUsd"] = UNKNOWN
    wall = round(clock() - started, 1)
    tokens, claude_cost, models = claude_usage(run["home"], driven["sessions"])
    codex_model = arm.get("reviewer", {}).get("model") if arm["arm"] == "crew" else None
    codex_tokens, codex_cost_usd = codex_usage(run["repo"], run["home"], codex_model,
                                               os.path.join(run["proxylog"], "proxy.jsonl"))
    own_cost = add_costs(claude_cost, codex_cost_usd)
    cost = add_costs(own_cost, carried_cost) if carried_cost != UNKNOWN else UNKNOWN
    failure = driven["failure"]
    try:
        reasons = contamination(task, run["home"], run["repo"], os.path.join(run["proxylog"], "proxy.jsonl"), arm,
                                ctx["source_repo"])
        check_failed = False
    except Exception as exc:  # noqa: BLE001 - the attempt is paid for: its row is written whatever the check raised; pylint: disable=broad-exception-caught
        reasons, check_failed = [], True
        failure = failure or f"contamination check raised {type(exc).__name__}: {exc}"
    if check_failed:
        status = "error"
    elif driven["failure"]:
        status = "unscorable"
    elif reasons:
        status = "contaminated"
    else:
        status = "scored"
    graded = {"escapedDefects": None, "defectsTotal": len(task["defects"]), "regressionTestsFailed": None}
    if status not in ("unscorable", "error"):
        try:
            try:
                graded = grade(task, run["repo"], ctx["source_repo"], ctx["docker"])
            except GradingInfra:
                # grading is cheap next to the paid arm: one retry before the run is called unscored
                graded = grade(task, run["repo"], ctx["source_repo"], ctx["docker"])
        except GradingInfra as exc:
            # not a verdict on the code: unscored, with the cost the arm already spent
            status, failure = "infra", f"grading infra failure: {exc}"
        except Exception as exc:  # noqa: BLE001 - the attempt is paid for: its row is written whatever grading raised; pylint: disable=broad-exception-caught
            status, failure = "error", f"grading raised {type(exc).__name__}: {exc}"
    return {"task": task["name"], "bucket": task["bucket"], "arm": arm["arm"], "attempt": attempt,
            "runStatus": status, "escapedDefects": graded["escapedDefects"],
            "defectsTotal": graded["defectsTotal"], "regressionTestsFailed": graded["regressionTestsFailed"],
            "reviewCycles": driven["cycles"], "reviewAttemptsIncomplete": driven["incomplete"],
            "tokens": tokens, "claudeCostUsd": claude_cost, "codexTokens": codex_tokens,
            "codexCostUsd": codex_cost_usd, "costUsd": cost, "ownCostUsd": own_cost,
            "cliTotalCostUsd": driven["cliTotalCostUsd"], "wallSeconds": wall, "exit": driven["exit"],
            "endedBy": driven["endedBy"], "failure": failure, "contamination": reasons,
            "unpriced": models if models else [],
            "runDir": run["dir"]}


def run_chain(ctx, task, arm):
    """One scored-or-exhausted chain: an unscorable attempt is rerun once and its
    cost is carried into the rerun; a chain that ends unscorable keeps its spend
    as `unscoredSpendUsd`."""
    first = run_once(ctx, task, arm, 1)
    append_result(ctx["results"], first)
    if first["runStatus"] != "unscorable":
        return first
    guard = ctx.get("before_rerun")
    if guard:
        try:
            guard()
        except BaseException as exc:
            # the chain ends here: its paid first attempt is recorded as unscored spend, once
            append_result(ctx["results"], {
                "task": first["task"], "bucket": first["bucket"], "arm": first["arm"], "attempt": 1,
                "runStatus": "unscorable", "ownCostUsd": 0.0, "costUsd": 0.0,
                "unscoredSpendUsd": first["ownCostUsd"], "failure": f"rerun refused: {exc}"})
            raise
    carried = first["ownCostUsd"]
    second = run_once(ctx, task, arm, 2, carried)
    if second["runStatus"] == "unscorable":
        second["unscoredSpendUsd"] = second["costUsd"]
        second["costUsd"] = UNKNOWN if second["costUsd"] == UNKNOWN else 0.0
    append_result(ctx["results"], second)
    return second


# --------------------------------------------------------------------------
# report

def known(value):
    return value is not None and value != UNKNOWN


def bucket_verdict(rows, bucket):
    """The per-bucket verdict dict from results rows (spec Acceptance 10)."""
    result = {"bucket": bucket, "tasks": [], "dropped": [], "contaminated": [], "lines": [],
              "regressions": {}, "verdict": "could not tell"}
    mine = [r for r in rows if r.get("bucket") == bucket]
    result["contaminated"] = sorted({(r["task"], r["arm"], r["attempt"]) for r in mine
                                     if r.get("runStatus") == "contaminated"})
    scored = [r for r in mine if r.get("runStatus") == "scored"]
    for arm in ARMS:
        values = [r.get("regressionTestsFailed") for r in scored
                  if r["arm"] == arm and known(r.get("regressionTestsFailed"))]
        result["regressions"][arm] = statistics.median(values) if values else None
    unknown_cost = [r for r in mine if r.get("runStatus") == "scored" and not known(r.get("costUsd"))]
    unknown_chain = [r for r in mine if r.get("runStatus") == "unscorable" and r.get("unscoredSpendUsd") == UNKNOWN]
    tasks = sorted({r["task"] for r in mine})
    per_task = {}
    for task in tasks:
        arms_ok = {}
        for arm in ARMS:
            runs = [r for r in scored if r["task"] == task and r["arm"] == arm and known(r.get("costUsd"))
                    and known(r.get("escapedDefects"))]
            arms_ok[arm] = runs
        if any(len(runs) < 2 for runs in arms_ok.values()):
            result["dropped"].append(task)
            continue
        entry = {}
        for arm, runs in arms_ok.items():
            spend = sum(float(r["unscoredSpendUsd"]) for r in mine
                        if r["task"] == task and r["arm"] == arm and known(r.get("unscoredSpendUsd")))
            entry[arm] = {"defects": statistics.median(r["escapedDefects"] for r in runs),
                          "cost": statistics.median(float(r["costUsd"]) for r in runs) + spend}
        per_task[task] = entry
    result["tasks"] = sorted(per_task)
    capped = [r for r in scored if r.get("endedBy") == "resume-cap"]
    if capped:
        result["lines"].append(f"note: {len(capped)} crew run(s) were graded at the harness resume cap, not at an "
                               "autopilot stop (the arm was still asked for work)")
    unscored = [r for r in mine if r.get("runStatus") in ("infra", "error")]
    if unscored:
        names = ", ".join(sorted(f"{r.get('task')}/{r.get('arm')}" for r in unscored))
        result["lines"].append(f"could not tell: {len(unscored)} run(s) unscored by a grading infrastructure failure "
                               f"or error, not by the code under test ({names})")
        return result
    if unknown_cost or unknown_chain:
        result["lines"].append("could not tell: a cost input is UNKNOWN")
        return result
    if len(per_task) < 2:
        result["lines"].append(f"could not tell: {len(per_task)} task(s) with at least 2 known runs per arm (need 2)")
        return result
    defect_diff = statistics.median(e["crew"]["defects"] - e["baseline"]["defects"] for e in per_task.values())
    cost_diff = statistics.median(e["crew"]["cost"] - e["baseline"]["cost"] for e in per_task.values())
    result["defectDiff"], result["costDiff"] = defect_diff, cost_diff
    if defect_diff >= 0:
        result["verdict"] = "crew leaves no fewer escaped defects"
        result["lines"].append(f"crew leaves no fewer escaped defects (median defect difference {defect_diff:+g}, "
                               f"median cost difference {cost_diff:+.2f} USD)")
        return result
    avoided = -defect_diff
    if cost_diff <= 0:
        result["verdict"] = "crew pays for itself"
        result["lines"].append(f"crew costs no more and avoids {avoided:g} escaped defect(s) per task "
                               f"(cost difference {cost_diff:+.2f} USD): it pays for itself at any value")
    else:
        result["breakEvenUsd"] = round(cost_diff / avoided, 2)
        result["verdict"] = "break-even"
        result["lines"].append(f"crew pays for itself when a reader values one escaped defect above "
                               f"{result['breakEvenUsd']:.2f} USD (cost difference {cost_diff:+.2f} USD, "
                               f"{avoided:g} defect(s) avoided per task)")
    return result


def report_text(rows):
    out = ["# Outcome eval report", ""]
    total = 0.0
    unknown = False
    for row in rows:
        spend = spend_of(row)
        if spend == UNKNOWN:
            unknown = True
        else:
            total += spend
    shown = f"UNKNOWN (at least {total:.2f} USD known)" if unknown else f"{total:.2f} USD"
    out.append(f"Runs: {len(rows)}; total cost: {shown}")
    out.append("")
    for bucket in BUCKETS:
        verdict = bucket_verdict(rows, bucket)
        out.append(f"## Bucket {bucket}")
        if not any(r.get("bucket") == bucket for r in rows):
            out.append("could not tell: no tasks in this bucket")
        for line in verdict["lines"]:
            out.append(line)
        if verdict["tasks"]:
            out.append("Tasks counted: " + ", ".join(verdict["tasks"]))
        if verdict["dropped"]:
            out.append("Tasks dropped (fewer than 2 known runs in an arm): " + ", ".join(verdict["dropped"]))
        crew_reg, base_reg = verdict["regressions"]["crew"], verdict["regressions"]["baseline"]
        out.append(f"Regressions (median base-passing tests failed, beside the verdict, never folded in): "
                   f"crew {'UNKNOWN' if crew_reg is None else format(crew_reg, 'g')}, "
                   f"baseline {'UNKNOWN' if base_reg is None else format(base_reg, 'g')}")
        if verdict["contaminated"]:
            listed = ", ".join(f"{t}/{a}/attempt {n}" for t, a, n in verdict["contaminated"])
            out.append("Contaminated runs (excluded): " + listed)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
# commands

def selected_tasks(args):
    dirs = task_dirs(args.tasks_dir)
    tasks = [load_task(d) for d in dirs]
    if args.task:
        tasks = [t for t in tasks if t["name"] == args.task]
        if not tasks:
            fail(f"no task named {args.task} under {args.tasks_dir}")
    elif not args.all:
        fail("name a task with --task or pass --all")
    return tasks


def cmd_validate(args):
    check_method(args.eval_dir)
    tasks = selected_tasks(args)
    problems = []
    for task in tasks:
        problems.extend(validate_task(task, args.source_repo))
    if problems:
        for problem in problems:
            print("validate: " + problem, file=sys.stderr)
        return 1
    print(f"validate: {len(tasks)} task(s) ok")
    return 0


def canary_fingerprint(eval_dir):
    """What a canary vouches for besides the image: the proxy allowlist, the proxy and the
    in-container wrapper. Any change to them makes an earlier canary stale."""
    digest = hashlib.sha256()
    for name in ("proxy-allowlist.txt", "proxy.py", "eval-run.py"):
        try:
            with open(os.path.join(eval_dir, "container", name), "rb") as fh:
                digest.update(name.encode() + b"\0" + fh.read() + b"\0")
        except OSError as exc:
            fail(f"canary fingerprint: cannot read container/{name}: {exc}")
    return digest.hexdigest()


def canary_ok(results_path, docker=None, eval_dir=None):
    path = os.path.join(os.path.dirname(os.path.abspath(results_path)), "canary.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return False
    if not lines or CANARY_PASS not in lines[-1:]:
        return False
    if eval_dir is not None and f"fingerprint={canary_fingerprint(eval_dir)}" not in lines[0].split():
        return False
    if docker:
        # the canary vouches for one image: its first line records the id it ran against
        try:
            out = subprocess.run([docker, "image", "inspect", "-f", "{{.Id}}", IMAGE], capture_output=True,
                                 text=True, check=False, stdin=subprocess.DEVNULL, timeout=CLEANUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return False
        return out.returncode == 0 and f"image={out.stdout.strip()}" in lines[0].split()
    return True


def lock_results(results_path):
    """An exclusive lock for the life of a `run`: two harness processes on one results
    file would each pass the budget check before either appended."""
    # POSIX only, like the suite
    import fcntl  # pylint: disable=import-outside-toplevel
    # held until the run ends, so not a `with` block
    handle = open(results_path + ".lock", "w", encoding="utf-8")  # noqa: SIM115  # pylint: disable=consider-using-with
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        fail(f"another run is using {results_path} (lock held); the budget is checked per process")
    return handle


def cmd_run(args):
    arms = check_method(args.eval_dir)
    tasks = selected_tasks(args)
    docker = which("docker")
    if not canary_ok(args.results, docker, args.eval_dir):
        fail("no passing canary for the current image: run evals/crew-outcome/container/canary.sh and keep its "
             "output as canary.txt beside the results file")
    ctx = {"docker": docker, "source_repo": args.source_repo, "runs_dir": args.runs_dir,
           "results": args.results, "crew_plugin": args.crew_plugin,
           "container_dir": os.path.join(args.eval_dir, "container")}
    os.makedirs(args.runs_dir, exist_ok=True)
    lock = lock_results(args.results)
    chosen = [args.arm] if args.arm else list(ARMS)
    for task in tasks:
        for arm_name in chosen:
            for _ in range(args.runs):
                def check(bucket=task["bucket"], name=arm_name):
                    return budget_check(read_results(args.results), bucket, name, args.max_cost_usd,
                                        args.first_run_estimate_usd)
                check()
                ctx["before_rerun"] = check
                row = run_chain(ctx, task, arms[arm_name])
                print(f"run: {row['task']} {row['arm']} -> {row['runStatus']} cost={row['costUsd']}")
    lock.close()
    return 0


def cmd_report(args):
    rows = read_results(args.results)
    sys.stdout.write(report_text(rows))
    return 0


def positive_amount(text):
    """A finite amount above zero: NaN or infinity would make every budget comparison false."""
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"{text!r} must be a finite amount above zero")
    return value


def build_parser():
    parser = argparse.ArgumentParser(prog="crew-outcome-eval.py", description=__doc__.split("\n", maxsplit=1)[0])
    parser.add_argument("--eval-dir", default=EVAL_DIR)
    parser.add_argument("--tasks-dir", default=None)
    parser.add_argument("--source-repo", default=REPO)
    sub = parser.add_subparsers(dest="command", required=True)
    val = sub.add_parser("validate")
    val.add_argument("--task")
    val.add_argument("--all", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("--task")
    run.add_argument("--all", action="store_true")
    run.add_argument("--arm", choices=ARMS)
    run.add_argument("--runs", type=int, default=2)
    run.add_argument("--results", required=True)
    run.add_argument("--runs-dir", required=True)
    run.add_argument("--crew-plugin", default=os.path.join(REPO, "plugin", "crew"))
    run.add_argument("--max-cost-usd", type=positive_amount, default=DEFAULT_MAX_COST_USD)
    run.add_argument("--first-run-estimate-usd", type=positive_amount, default=DEFAULT_FIRST_RUN_ESTIMATE_USD)
    rep = sub.add_parser("report")
    rep.add_argument("--results", required=True)
    return parser


def main(argv):
    args = build_parser().parse_args(argv)
    if args.tasks_dir is None:
        args.tasks_dir = os.path.join(args.eval_dir, "tasks")
    try:
        with contextlib.suppress(AttributeError):
            if args.command == "run" and args.runs < 1:
                fail("--runs must be at least 1")
        return {"validate": cmd_validate, "run": cmd_run, "report": cmd_report}[args.command](args)
    except EvalError as exc:
        print(f"crew-outcome-eval: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
