#!/usr/bin/env python3
"""One local gate runner for this repository: the whole PR-path CI suite, run
the way a lane needs it, with one status file.

Run: python3 scripts/gate-runner.py            (the whole table)
     python3 scripts/gate-runner.py --list     (what it would run)
     python3 scripts/gate-runner.py --check-ci (is the table still CI's?)

Three phases, in order:
  cheap  every quick check, serially, directly -- never under heavy-run, so a
         one-second check never queues for a heavy slot;
  heavy  two groups, A and B, run AT THE SAME TIME inside ONE heavy-run call
         (one slot, one 6G cgroup); each group is serial within itself;
  solo   after both groups finish, inside that same call: the `wallclock`
         pytest set (asserts elapsed time, so it cannot share the CPU with
         xdist workers -- plugin/crew/tests/conftest.py) and sabotage.py (it
         edits real source in place, so nothing else may read the tree).

heavy-run is found from HEAVY_RUN: unset = /root/crew-tmp/heavy-run when that
is executable, else absent; `none` = absent; any other value must be an
executable or the run refuses (exit 2). Absent means the heavy phase runs
directly and the run SAYS so: `heavy_run: absent (uncapped)`. This runner
never sets HEAVY_RUN_NOCAP or HEAVY_RUN_MEM.

Every pytest step except `wallclock` carries a literal `-n 4`. If pytest-xdist
is not importable those steps are COULD-NOT-TELL; they never fall back to a
serial run.

States: PASS (rc 0), FAIL (rc non-zero, the step completed), SKIP (rc 77, or a
tool the step needs is missing -- NOT VERIFIED), COULD-NOT-TELL (timed out,
killed by a signal incl. rc 137/143, could not start, or no result recorded).
A timeout kills the step's whole process group: SIGTERM, a grace period
(--grace, default 30 s) that lasts until the whole GROUP is gone, not just its
leader, then SIGKILL. A heavy-run call that dies leaves every heavy/solo step
it had not recorded COULD-NOT-TELL, and a heavy-part.json result is taken only
for a table step, under its own name, carrying that step's phase, group, cwd
and timeout and an argv list, with a state its rc could give (PASS needs rc 0,
FAIL an rc classify() calls FAIL, SKIP rc 77 or null) -- anything else is
COULD-NOT-TELL. The inner
runner refuses (exit 2, no step run) unless the table it loads has the digest
the outer runner validated (--table-digest), so a table or runner file edited
by a cheap step never runs.

Overall and exit: any FAIL = FAIL, exit 1; else any COULD-NOT-TELL, or no step
PASSED at all = COULD-NOT-TELL, exit 3; else PASS, exit 0. Usage error or
refusal = exit 2. The last stdout line counts every SKIP and says when the
table or the step set is not the repo gate (--table, --only).

Status: one JSON file, <out>/status.json, default out
$TMPDIR/gate-runner/<shortsha>-<utc>/ (claimed with mkdir, so two runs in one
second get two directories), rewritten (temp file + os.replace) after every
step -- a heavy step's result is copied in from heavy-part.json as soon as the
inner runner records it, not when the heavy-run call ends; per-step logs
under <out>/logs/. --skip records SKIP before anything about the step is built
or probed.

A --table step is refused (exit 2) unless its name matches _NAME and is not
reserved (it becomes a log path), its keys are known, every field has its
type, a heavy step's group is A or B and any other step has none, and its cwd
resolves inside --root. The cwd is resolved again when the step launches (an
earlier step may have swapped it for a symlink); outside --root then is
COULD-NOT-TELL. On Linux the checked directory is opened, the opened directory
is checked again, and the child starts in it through /proc/self/fd, so a later
swap of the pathname cannot redirect it; elsewhere (no /proc/self/fd) the
child gets the resolved path and a swap in between is not prevented. A tool
named in `needs` is run by its absolute path; a `module:<name>` need is a
Python module this interpreter must import, else the step is SKIP (L-0657).

The table is derived from .github/workflows/; `--check-ci` (and
scripts/_test/gate-runner.py) fails when a workflow `run:` command is in
neither the table nor EXCLUDED_CI, or a workflow file is unclassified. Each
`run:` line is split into simple commands (on ; && || |, quote-aware), so a
check chained onto an install or inside a one-line if/while/for still counts.
No job is excluded whole; a step is excluded only by a WINDOWS_ONLY_IFS
condition. The check is one-way: table steps CI does not run (sabotage.py,
ruff-no-new, check-tooling-pr) are allowed.

Map mode (opt-in, nothing calls it yet; R-81 wires the verify gate to it):
  python3 scripts/gate-runner.py --map .crew/verify.json --changed-file F|- [--tier fast|heavy|all]
  python3 scripts/gate-runner.py --map .crew/verify.json --base REF --slice K/N [--plan]
selects the rules of the .crew/verify.json map that the changed set requires
(the matcher of verify-gate.sh; bookkeeping paths dropped; an unmatched path is
unmapped unless a refresh artifact; `always`; `default` exactly when nothing is
left to run after `always` and reach exclusion; `unmapped` read from the parsed
top-level key, an unknown value failing closed -- verify-gate greps the literal
"fail", a recorded divergence), then runs ONE tier per round or ONE
deterministic slice K of N of the whole selected set. Selection never drops what
the map requires: --tier fast lists every matched heavy unit under other_tier
(SKIP, NOT VERIFIED - heavy, runs at Gate) and --tier heavy does the same for the
fast ones; the last stdout line counts them. A rule is `fast` only by a
measurement on THIS machine (.crew/.verify-gate.timings.json) below
--fast-seconds (default 120); declared `seconds` alone is heavy. A slice
partitions every matched rule (reach-excluded and requiresCleanTree ones too,
exclusions are applied inside the slice as SKIP NOT VERIFIED) by declared
`seconds` only, longest first onto the lightest slice, so every machine computes
the same partition from the map bytes and the changed list alone; @always,
@default and @unmapped are always slice 1. A rule with a valid `coveredBy` joins
its superset's unit and is credited (PASS, credited_by) only when the superset
is PASS in this run, PYTEST_ADDOPTS is empty and the tree snapshots before the
superset and before the credit are equal; otherwise it runs as itself.
status.json gains `map`: head, changed_digest, map_digest, partition_digest
(R-81 checks that n slices share all four and that their unit lists are disjoint
and union to the selection), workers, units, other_tier, carried (preReview is
carried, run by review_run.py, never counted as PASS). Heavy-tier units and
every slice unit run in the ONE heavy-run call (--map-inner, refused unless the
plan file has the digest the outer wrote); fast-tier units run directly, at most
--workers at once (default probed: min(cpus, MemAvailable / 1.5 GiB, 4); any
probe failure is 1, said on stderr). PASS prints one line; anything else prints
each FAIL or COULD-NOT-TELL unit and the last 20 lines of its failing log, then
the same count line. Trust: the map's `run` strings execute here without
verify_trust.py's check -- use this runner on this repo's own map only until
R-81 owns trust. Not run on Windows here: INFERRED that `bash -c` resolves as the
table steps' `bash` does.

Windows: the kill path uses CREATE_NEW_PROCESS_GROUP and `taskkill /T`. Not
verified on a Windows host.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
DEFAULT_HEAVY_RUN = "/root/crew-tmp/heavy-run"
DEFAULT_RUFF_NO_NEW = "/root/crew-tmp/ruff-no-new.py"
WINDOWS_PWSH = "C:/Program Files/PowerShell/7/pwsh.exe"

PASS, FAIL, SKIP, CNT = "PASS", "FAIL", "SKIP", "COULD-NOT-TELL"
EXIT_PASS, EXIT_FAIL, EXIT_USAGE, EXIT_CNT, EXIT_SKIP = 0, 1, 2, 3, 77
SIGNAL_RCS = {129: "SIGHUP", 130: "SIGINT", 131: "SIGQUIT", 134: "SIGABRT",
              137: "SIGKILL (a memory cap or OOM kill looks like this)", 139: "SIGSEGV",
              143: "SIGTERM"}
PHASES = ("cheap", "heavy", "solo")
SLOT_WAIT_ALLOWANCE = 3600
# The wait after the final SIGKILL is a wait too: a child stuck in uninterruptible
# I/O may never be reaped, and the step is then COULD-NOT-TELL, not a hang.
KILL_REAP_SECONDS = 10


@dataclass(frozen=True)
class Step:
    name: str
    phase: str
    argv: tuple
    group: str | None = None
    cwd: str = "."
    timeout: int = 300
    needs: tuple = ()
    pytest: bool = False
    ci: tuple = ()


PY = "{python}"
COMBINED_DIRS = ("plugin/crew/tests/", "plugin/gizmoduck/scripts/_test/",
                 "skills/mermaid-svg-bitbucket/tests/", "skills/notify/tests/",
                 "skills/doc-builder/scripts/_test/", "skills/intune-graph/scripts/_test/",
                 "skills/windows-ssm/tests/")
NO_CACHE = ("-p", "no:cacheprovider")
# What pytest resolves on its own for the whole COMBINED_DIRS list, pinned so
# a subset run (C-0001) is the same session: gizmoduck's ini sets the rootdir,
# pythonpath and addopts for every suite in the run.
COMBINED_CONFIG = ("-c", "plugin/gizmoduck/pytest.ini", "--rootdir", "plugin/gizmoduck")


def _py_suite(name: str, path: str, workflow: str = "marketplace.yml") -> Step:
    return Step(name, "cheap", (PY, path), ci=((workflow, f"python3 {path}"),))


def _bash_suite(name: str, path: str, workflow: str, phase: str = "cheap",
                group: str | None = None, timeout: int = 300, ci_cmd: str | None = None) -> Step:
    return Step(name, phase, ("bash", path), group=group, timeout=timeout, needs=("bash",),
                ci=((workflow, ci_cmd or f"bash {path}"),))


TABLE = (
    Step("check-marketplace", "cheap", (PY, "scripts/check-marketplace.py"),
         # L-0511: CI passes --pending-bump on a draft PR only. A lane runs the
         # full check (the stricter one), so the draft invocation is pinned here too.
         ci=(("marketplace.yml", "python3 scripts/check-marketplace.py"),
             ("marketplace.yml", "python3 scripts/check-marketplace.py --pending-bump"))),
    _py_suite("draft-check-name", "scripts/_test/draft-check-name.py"),
    _py_suite("argument-hint-frontmatter", "scripts/_test/argument-hint-frontmatter.py"),
    _py_suite("self-claims", "scripts/_test/self-claims.py"),
    _py_suite("crew-ignore-policy", "scripts/_test/crew-ignore-policy.py"),
    _py_suite("codemap-coverage", "scripts/_test/codemap-coverage.py"),
    _py_suite("verifying-doc", "scripts/_test/verifying-doc.py"),
    _py_suite("check-diagram-embeds", "scripts/_test/check-diagram-embeds.py"),
    _py_suite("plugin-evals-runner", "scripts/_test/plugin-evals-runner.py"),
    _py_suite("crew-outcome-eval", "scripts/_test/crew-outcome-eval.py"),
    _py_suite("version-drift", "scripts/_test/version-drift.py"),
    _py_suite("shellcheck-directives", "scripts/_test/shellcheck-directives.py"),
    _py_suite("windows-shards", "scripts/_test/windows-shards.py"),
    _py_suite("crew-docs-suite", "scripts/_test/crew-docs.py"),
    _py_suite("autopilot-guide", "scripts/_test/autopilot-guide.py"),
    # T-0055. Locally it sees commit trailers only; CI also reads the PR body.
    # Locally its base is the nearest of origin/main and origin/release/*.
    Step("check-crew-docs", "cheap", (PY, "scripts/check-crew-docs.py"),
         ci=(("marketplace.yml", "python3 scripts/check-crew-docs.py"),)),
    _py_suite("ci-select", "scripts/_test/ci-select.py"),
    _py_suite("instruction-budgets-suite", "scripts/_test/instruction-budgets.py",
              "instruction-budgets.yml"),
    Step("sync-updates", "cheap", (PY, "scripts/sync-updates.py", "--check"),
         ci=(("marketplace.yml", "python3 scripts/sync-updates.py --check"),)),
    # L-0657: the committed crew guide HTML and the generated configuration
    # reference match their sources. build.py needs markdown: SKIP without it,
    # never PASS. config_reference.py imports only the standard library.
    Step("crew-guides-fresh", "cheap", (PY, "docs/guides/crew/src/build.py", "--check"),
         needs=("module:markdown",),
         ci=(("marketplace.yml", "python3 docs/guides/crew/src/build.py --check"),)),
    Step("crew-config-reference-fresh", "cheap",
         (PY, "docs/guides/crew/src/config_reference.py", "--check"),
         ci=(("marketplace.yml", "python3 docs/guides/crew/src/config_reference.py --check"),)),
    # L-0718: the generated review rules match crew's standards. Was local-only
    # (verify.json `standards-export`) until PR #754 went green with stale ones.
    _py_suite("standards-export-ci-suite", "scripts/_test/standards-export-ci.py"),
    Step("standards-export", "cheap",
         (PY, "plugin/crew/hooks/scripts/crew_standards.py", "export", "--check", "--root", "."),
         ci=(("marketplace.yml",
              "python3 plugin/crew/hooks/scripts/crew_standards.py export --check --root ."),)),
    _py_suite("sync-updates-suite", "scripts/_test/sync-updates.py"),
    # Every version the branch sets owes a CHANGELOG.md entry or a `re-bump only`
    # line. A missing origin/main is exit 77, recorded as SKIP, never PASS.
    Step("check-changelog", "cheap", (PY, "scripts/check-changelog.py"),
         ci=(("marketplace.yml", "python3 scripts/check-changelog.py"),)),
    _py_suite("check-changelog-suite", "scripts/_test/check-changelog.py"),
    Step("install-prerequisites-syntax", "cheap", ("bash", "-n", "scripts/install-prerequisites.sh"),
         needs=("bash",), ci=(("marketplace.yml", "bash -n scripts/install-prerequisites.sh"),)),
    _bash_suite("menu-groups", "scripts/_test/menu-groups.sh", "marketplace.yml",
                ci_cmd="./scripts/_test/menu-groups.sh"),
    _bash_suite("check-powershell-suite", "scripts/_test/check-powershell.sh", "marketplace.yml"),
    _bash_suite("pwsh-isolated", "scripts/_test/pwsh-isolated.sh", "marketplace.yml"),
    _bash_suite("ps-install-keys", "scripts/_test/ps-install-keys.sh", "marketplace.yml"),
    _bash_suite("uv-install", "scripts/_test/uv-install.sh", "marketplace.yml"),
    _bash_suite("smoke", "_verify/smoke.sh", "marketplace.yml"),
    _bash_suite("mcp-preflight-catalog", "scripts/_test/mcp-preflight-catalog.sh", "marketplace.yml"),
    Step("validate-prompts", "cheap", (PY, "hooks/scripts/_test/validate-prompts.py"),
         cwd="plugin/crew",
         ci=(("marketplace.yml", "python3 hooks/scripts/_test/validate-prompts.py"),)),
    # Through the launcher (T-0506): a private startup-profile cache per pwsh run.
    # No `pwsh` need: the launcher resolves $PWSH, pwsh, pwsh.exe and the Windows
    # install paths itself, and exits 77 (SKIP) when none runs.
    Step("check-powershell", "cheap",
         ("bash", "scripts/pwsh-isolated.sh", "-NoProfile", "-File", "scripts/check-powershell.ps1"),
         needs=("bash",), ci=(("marketplace.yml", "./scripts/check-powershell.ps1"),)),
    Step("check-instructions", "cheap", (PY, "scripts/check_instructions.py"),
         ci=(("instruction-budgets.yml", "python3 scripts/check_instructions.py"),
             ("instruction-budgets.yml", 'python3 scripts/check_instructions.py --base "$BASE"'))),
    _bash_suite("bitbucket-merge-gate", "skills/bitbucket/scripts/_test/merge_gate.sh",
                "shell-suites.yml"),
    _bash_suite("doc-builder-checklist", "skills/doc-builder/scripts/_test/checklist.sh",
                "shell-suites.yml"),
    _bash_suite("jira-manager-jq-absence", "skills/jira-manager/scripts/_test/jq_absence.sh",
                "shell-suites.yml"),
    Step("ruff", "cheap", ("ruff", "check", "."), needs=("ruff",),
         ci=(("pylint.yml", "ruff check ."),)),
    Step("ruff-no-new", "cheap", (PY, "{ruff_no_new}", "{root}"), needs=("path:{ruff_no_new}",)),
    Step("check-tooling-pr", "cheap", (PY, "scripts/check-tooling-pr.py")),

    Step("pytest-combined", "heavy",
         (PY, "-m", "pytest", *COMBINED_DIRS, *COMBINED_CONFIG, "-n", "4", "-m", "not wallclock",
          *NO_CACHE),
         group="A", timeout=1800, pytest=True,
         # CI runs the subset scripts/ci-select.py picks (C-0001), falling
         # back to all of COMBINED_DIRS; its suite checks that list.
         ci=(("pytest-crew.yml", "pytest ${PYTEST_COMBINED:-" + " ".join(COMBINED_DIRS) + "} "
              + " ".join(COMBINED_CONFIG) + ' -n 16 --dist worksteal -m "not wallclock" -v'),)),
    # crew-shell-matrix's ubuntu leg: the full bash/pwsh hook matrix, which
    # plugin/crew/tests/conftest.py deselects from every run not naming `slow`.
    # 201.8s under heavy-run, 1690 passed / 22 skipped (2026-10-01).
    Step("pytest-crew-slow", "heavy",
         (PY, "-m", "pytest", "plugin/crew/tests/", "-m", "slow", "-n", "4", *NO_CACHE),
         group="A", timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "python -m pytest plugin/crew/tests -m slow -n 8 -v"),)),

    _bash_suite("crew-run-tests", "plugin/crew/hooks/scripts/_test/run-tests.sh", "marketplace.yml",
                phase="heavy", group="B", timeout=900),
    _bash_suite("obsidian-vault-run-tests", "plugin/obsidian-vault/hooks/scripts/_test/run-tests.sh",
                "shell-suites.yml", phase="heavy", group="B", timeout=900),
    Step("pylint", "heavy", ("pylint", "-j", "4", "{git_py_files}"), group="B", timeout=900,
         needs=("pylint",),
         ci=(("pylint.yml", "pylint -j \"$(python -c 'import os; print(os.cpu_count() or 1)')\" "
              "$(git ls-files '*.py')"),)),
    Step("pytest-cisco-meraki", "heavy",
         (PY, "-m", "pytest", "skills/cisco-meraki/tests/", "-n", "4", *NO_CACHE),
         group="B", timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "pytest skills/cisco-meraki/tests/ -v"),)),
    Step("pytest-wazuh-onprem", "heavy",
         (PY, "-m", "pytest", "skills/wazuh-onprem/scripts/_test/", "-n", "4", *NO_CACHE),
         group="B", timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "pytest skills/wazuh-onprem/scripts/_test/ -v"),)),
    Step("mcp-servers-npm-test", "heavy", ("npm", "test"), group="B", cwd="mcp-servers", timeout=900,
         needs=("npm", "path:mcp-servers/node_modules"), ci=(("mcp-servers.yml", "npm test"),)),

    Step("wallclock", "solo", (PY, "-m", "pytest", "plugin/crew/tests/", "-m", "wallclock", *NO_CACHE),
         timeout=900, pytest=True,
         ci=(("pytest-crew.yml", "pytest plugin/crew/tests/ -m wallclock -v"),)),
    Step("sabotage", "solo", (PY, "plugin/crew/tests/sabotage.py"), timeout=5400),
)

INCLUDED_WORKFLOWS = ("instruction-budgets.yml", "marketplace.yml", "mcp-servers.yml",
                      "pylint.yml", "pytest-crew.yml", "shell-suites.yml")
EXCLUDED_WORKFLOWS = (
    ("plugin-evals.yml", "real, billed model calls behind a repository secret"),
    ("pytest-ai-connect.yml", "needs the ai-connect plugin's own pinned dependencies, which the lane's python3 "
                              "lacks; .crew/verify.json's plugin/ai-connect rule runs the same two commands"),
    ("publish-mcp-servers.yml", "tag-only npm publish; its npm test is mcp-servers.yml's"),
    ("runner-autostart.yml", "dispatches a start of the self-hosted runner host; checks nothing"),
    ("verify-gate.yml", "runs verify-gate.sh --all on the self-hosted pool and uploads its receipt "
                        "(L-0555); the lane's own gate is that same command, not a CI suite"),
)
# A step is excluded by its `if:` only when that condition confines it to a
# leg this runner does not have. Whole jobs are never excluded: a job's legs
# change (crew-shell-matrix is ubuntu-only today) and its other steps still run.
# The crew-windows-* jobs (L-0577) run only on windows-latest, and each of
# their `run:` steps carries this condition so the job's own steps say so.
WINDOWS_ONLY_IFS = (
    ("runner.os == 'Windows'",
     "runs only in a crew-windows-* job (L-0577); this runner is not Windows"),
)
INSTALL = "an install step, not a check"
EXCLUDED_CI = (
    ("marketplace.yml", "python -m pip install *", INSTALL),
    ("marketplace.yml", "npm install -g @anthropic-ai/claude-code@*", INSTALL),
    ("marketplace.yml", "claude plugin validate --strict *",
     "CI pins the Claude Code CLI version; a lane's CLI differs, so its verdict is not CI's"),
    ("pylint.yml", "python -m pip install *", INSTALL),
    ("pylint.yml", "pip install *", INSTALL),
    ("pylint.yml", "pylint --version", "prints a version"),
    ("pylint.yml", "ruff --version", "prints a version"),
    ("pytest-crew.yml", "python -m pip install *", INSTALL),
    ("pytest-crew.yml", "pip install *", INSTALL),
    ("pytest-crew.yml",
     "changed=$(git diff --name-only HEAD^1 HEAD -- plugin/crew .github/workflows/pytest-crew.yml)",
     "crew-windows-decide: whether the Windows jobs run on a PR (T-0110, L-0577); checks nothing"),
    ("pytest-crew.yml", "python3 scripts/check-windows-shards.py *",
     "the Windows fan-in (L-0577): reads CI job results and artifacts, which a lane does not "
     "have; its suite scripts/_test/windows-shards.py is the windows-shards step"),
    ("mcp-servers.yml", "npm ci", INSTALL + "; the npm test step SKIPs without node_modules"),
) + tuple(
    (wf, "python3 scripts/ci-select.py *",
     "C-0001: which suites a PR selects, from its diff; checks nothing. A lane runs every "
     "suite; its suite scripts/_test/ci-select.py is the ci-select step")
    for wf in ("pytest-crew.yml", "pylint.yml", "shell-suites.yml", "mcp-servers.yml"))


class Refusal(Exception):
    """A usage error or refusal: exit 2."""


class CannotStart(Exception):
    """A step's command could not be built or launched."""


# ---- process handling -----------------------------------------------------

STOP = threading.Event()
# The first signal that set STOP; the inner runner exits 128+signum with it, so
# the outer status never records a signal-stopped heavy-run call as rc=0.
STOP_SIGNAL: list = []
_LIVE: set = set()
_LIVE_LOCK = threading.Lock()


def _group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _signal_group(proc: subprocess.Popen, hard: bool) -> None:
    """Signal the step's process group -- but never once its leader has been
    reaped: from then on the leader's PID, and with it the group ID, may already
    belong to an unrelated process group (review r6 BLOCK)."""
    if proc.returncode is not None:
        return
    if os.name == "nt":
        cmd = ["taskkill", "/T", "/PID", str(proc.pid)] + (["/F"] if hard else [])
        try:
            subprocess.run(cmd, capture_output=True, check=False, stdin=subprocess.DEVNULL,
                           timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        if hard and proc.poll() is None:
            # No group to signal (it was never made, or is gone): kill the
            # child itself, so the caller's wait() cannot block forever.
            try:
                proc.kill()
            except OSError:
                pass


def _group_has_live_member(pgid: int):
    """Linux: whether any non-zombie process is in group `pgid`, from /proc --
    the leader is kept unreaped (a zombie) while the group is signalled, and
    signal 0 counts a zombie as a member. None where /proc cannot say."""
    try:
        names = os.listdir("/proc")
    except OSError:
        return None
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", "rb") as fh:
                fields = fh.read().rsplit(b")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(fields) > 2 and fields[2] == str(pgid).encode() and fields[0] not in (b"Z", b"X"):
            return True
    return False


def _group_alive(proc: subprocess.Popen) -> bool:
    """Whether any process of the step's group is still there. POSIX asks the
    group itself (signal 0), so a grandchild that outlived its leader counts;
    on Linux, while the leader is unreaped, /proc answers instead so the zombie
    leader itself does not count. Windows has no group probe and falls back to
    the leader."""
    if os.name == "nt":
        return proc.poll() is None
    if proc.returncode is None and os.path.isdir("/proc/self"):
        live = _group_has_live_member(proc.pid)
        if live is not None:
            return live
    try:
        os.killpg(proc.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _leader_exited(proc: subprocess.Popen) -> bool:
    """Whether the step's leader has exited, WITHOUT reaping it where POSIX
    allows (waitid WNOWAIT): an unreaped leader keeps its PID, and so the
    group ID, from being reused, which is what keeps signalling the group safe.
    Where that cannot be asked (Windows, no os.waitid, not our child) it falls
    back to poll(), which reaps -- and _signal_group then stands down."""
    if proc.returncode is not None:
        return True
    if os.name == "nt" or not hasattr(os, "waitid"):
        return proc.poll() is not None
    try:
        info = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:
        return proc.poll() is not None
    return info is not None


def _reap(proc: subprocess.Popen) -> None:
    try:
        proc.wait(timeout=KILL_REAP_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def _kill_group(proc: subprocess.Popen, grace: float) -> bool:
    """SIGTERM the whole group and give the WHOLE group `grace` to exit -- not
    just the leader, so a grandchild still cleaning up is not SIGKILLed the
    moment its leader is gone; SIGKILL whatever is left, then sweep once more.
    The leader is reaped only after the last signal, so every signal reaches
    this step's group and never a later owner of its PGID (review r6 BLOCK).
    True when the leader exited and was reaped; False when it was still there
    KILL_REAP_SECONDS after SIGKILL (the caller records COULD-NOT-TELL)."""
    _signal_group(proc, hard=False)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if _leader_exited(proc) and not _group_alive(proc):
            _reap(proc)
            return True
        time.sleep(0.1)
    _signal_group(proc, hard=True)
    deadline = time.monotonic() + KILL_REAP_SECONDS
    exited = _leader_exited(proc)
    while not exited and time.monotonic() < deadline:
        time.sleep(0.05)
        exited = _leader_exited(proc)
    _signal_group(proc, hard=True)
    if exited:
        _reap(proc)
    return exited


def _not_reaped(what: str) -> str:
    return (f"{what}; process group sent SIGKILL and did not exit within "
            f"{KILL_REAP_SECONDS:g}s")


def spawn_and_wait(argv: list, cwd: str, log: str, timeout: float, grace: float,
                   env: dict | None = None, on_tick=None):
    """Run argv in its own process group, output to `log`, no pipes (an orphan
    holding a pipe would hang the caller). Returns (rc, timed_out, started, note)."""
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "wb") as fh:
        try:  # not `with`: the loop below waits on it and owns killing its group
            # pylint: disable-next=consider-using-with
            proc = subprocess.Popen(argv, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, **_group_kwargs())
        except (OSError, ValueError) as exc:
            return None, False, False, f"could not start: {exc}"
        with _LIVE_LOCK:
            _LIVE.add(proc)
        try:
            deadline = time.monotonic() + timeout
            stopped_at = killed_at = None
            while True:
                try:
                    return proc.wait(timeout=0.5), False, True, ""
                except subprocess.TimeoutExpired:
                    pass
                if on_tick is not None:
                    try:
                        on_tick()
                    # Any fault in the caller's merge must not orphan the group: the
                    # recovery is to kill it and say so (the caller marks COULD-NOT-TELL).
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        what = f"status merge failed ({exc!r})"
                        if not _kill_group(proc, grace):
                            return None, False, True, _not_reaped(what)
                        return None, False, True, f"{what}; process group killed"
                now = time.monotonic()
                if STOP.is_set():
                    if stopped_at is None:
                        stopped_at = now
                        _signal_group(proc, hard=False)
                    elif killed_at is None and now - stopped_at > grace:
                        killed_at = now
                        _signal_group(proc, hard=True)
                    elif killed_at is not None and now - killed_at > KILL_REAP_SECONDS:
                        return None, False, True, _not_reaped("runner stopped by a signal")
                if now >= deadline:
                    what = f"timed out after {timeout:g}s"
                    if not _kill_group(proc, grace):
                        return None, True, True, _not_reaped(what)
                    return (proc.returncode, True, True,
                            f"{what}; process group killed (SIGTERM, {grace:g}s grace, SIGKILL)")
        finally:
            with _LIVE_LOCK:
                _LIVE.discard(proc)


def _on_signal(signum, _frame) -> None:
    if not STOP_SIGNAL:
        STOP_SIGNAL.append(int(signum))
    STOP.set()
    with _LIVE_LOCK:
        live = list(_LIVE)
    for proc in live:
        _signal_group(proc, hard=False)
    print(f"gate-runner: received signal {signum}; stopping steps", file=sys.stderr, flush=True)


def install_signal_handlers() -> None:
    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _on_signal)
            except (ValueError, OSError):
                pass


# ---- classification -------------------------------------------------------

def classify(rc, timed_out: bool, started: bool):
    """(state, reason) from a step's outcome. Anything that is not a completed
    run with an exit status is COULD-NOT-TELL, never PASS (T-0082)."""
    if not started:
        return CNT, "could not start"
    if timed_out:
        return CNT, "timed out"
    if rc is None:
        return CNT, "no exit status recorded"
    if rc < 0:
        try:
            sig = signal.Signals(-rc).name
        except ValueError:
            sig = str(-rc)
        return CNT, f"killed by signal {sig}"
    if rc in SIGNAL_RCS:
        return CNT, f"exit {rc}: killed by {SIGNAL_RCS[rc]}"
    if rc == EXIT_SKIP:
        return SKIP, "exit 77: NOT VERIFIED"
    if rc == 0:
        return PASS, ""
    return FAIL, f"exit {rc}"


def overall(steps: list):
    """(state, exit code) for a run."""
    states = [s["state"] for s in steps]
    if FAIL in states:
        return FAIL, EXIT_FAIL
    if states and PASS in states and all(s in (PASS, SKIP) for s in states):
        return PASS, EXIT_PASS
    return CNT, EXIT_CNT


def write_status(path: str, data: dict) -> None:
    """Serialise first, then temp file + os.replace: a payload that cannot be
    written never truncates the previous status (CLAUDE.md, open() landmine)."""
    text = json.dumps(data, indent=2, sort_keys=False) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ---- table ----------------------------------------------------------------

# A step name becomes <out>/logs/<name>.log, so it may not carry a path
# separator, start with a dot, or be the outer heavy-run call's own log name.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESERVED_NAMES = ("heavy-run",)
TABLE_KEYS = frozenset(("name", "phase", "group", "argv", "cwd", "timeout", "needs", "pytest"))


def positive_finite(value) -> bool:
    """A JSON or CLI number usable as a duration: not bool, finite, > 0
    (json.load accepts NaN and Infinity, and 1e999 parses as inf)."""
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > 0)


def contained_cwd(root: str, cwd: str) -> str | None:
    """The real path (symlinks resolved) of a repository-relative step cwd, or
    None when cwd is absolute or that real path is outside the root's."""
    if os.path.isabs(cwd) or os.path.splitdrive(cwd)[0]:
        return None
    real_root = os.path.realpath(root)
    real = os.path.realpath(os.path.join(real_root, cwd))
    return real if _inside(real_root, real) else None


def _inside(real_root: str, real: str) -> bool:
    try:
        return os.path.commonpath([real_root, real]) == real_root
    except ValueError:  # different drives on Windows
        return False


def cwd_in_root(root: str, cwd: str) -> bool:
    return contained_cwd(root, cwd) is not None


def load_table(path: str | None, root: str = DEFAULT_ROOT):
    if path is None:
        return list(TABLE), "builtin"
    src = os.path.abspath(path)
    data = read_json(src)
    if data is None:
        raise Refusal(f"--table {path}: not readable JSON")
    raw = data.get("steps") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise Refusal(f"--table {path}: expected a list of steps or {{\"steps\": [...]}}")
    steps, seen = [], set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise Refusal(f"--table step {i}: not an object")
        name, phase, group = item.get("name"), item.get("phase"), item.get("group")
        argv = item.get("argv")
        if not isinstance(name, str) or not name or name in seen:
            raise Refusal(f"--table step {i}: missing or duplicate name")
        if not _NAME.match(name) or name in RESERVED_NAMES:
            raise Refusal(f"--table step {i}: name {name!r} must match {_NAME.pattern} and not be "
                          f"one of {RESERVED_NAMES} (it becomes <out>/logs/<name>.log)")
        unknown = sorted(set(item) - TABLE_KEYS)
        if unknown:
            raise Refusal(f"--table step {name}: unknown key(s) {', '.join(unknown)}")
        if phase not in PHASES:
            raise Refusal(f"--table step {name}: phase must be one of {PHASES}")
        if (group not in ("A", "B")) if phase == "heavy" else (group is not None):
            raise Refusal(f"--table step {name}: heavy steps need group A or B; cheap and solo "
                          "steps take no group (absent or null)")
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            raise Refusal(f"--table step {name}: argv must be a non-empty list of strings")
        timeout = item.get("timeout", 300)
        if not positive_finite(timeout):
            raise Refusal(f"--table step {name}: timeout must be a finite positive number")
        cwd, needs, pytest = item.get("cwd", "."), item.get("needs", []), item.get("pytest", False)
        if not isinstance(cwd, str) or not cwd:
            raise Refusal(f"--table step {name}: cwd must be a non-empty string")
        if not cwd_in_root(root, cwd):
            raise Refusal(f"--table step {name}: cwd {cwd!r} must be a directory inside --root "
                          "(relative, symlinks resolved)")
        if not isinstance(needs, list) or not all(isinstance(n, str) and n for n in needs):
            raise Refusal(f"--table step {name}: needs must be a list of non-empty strings")
        if not isinstance(pytest, bool):
            raise Refusal(f"--table step {name}: pytest must be true or false")
        seen.add(name)
        steps.append(Step(name, phase, tuple(argv), group=group, cwd=cwd, timeout=timeout,
                          needs=tuple(needs), pytest=pytest))
    return steps, src


def table_digest(steps: list) -> str:
    """sha256 over every field of every step of a loaded table (built-in or
    --table alike), so the inner runner can prove it loaded the table the
    outer runner validated."""
    text = json.dumps([dataclasses.asdict(s) for s in steps], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def phase_label(step: Step) -> str:
    return f"heavy {step.group}" if step.phase == "heavy" else step.phase


def print_list(steps: list) -> None:
    for step in steps:
        cwd = f" (cwd {step.cwd})" if step.cwd != "." else ""
        print(f"{phase_label(step):<8} {step.name:<28} timeout={step.timeout:>5}s  "
              f"{' '.join(step.argv)}{cwd}")


# ---- step execution -------------------------------------------------------

class Context:
    def __init__(self, root: str, out: str, grace: float, skip: set):
        self.root, self.out, self.grace, self.skip = root, out, grace, skip
        self.ruff_no_new = os.environ.get("RUFF_NO_NEW") or DEFAULT_RUFF_NO_NEW
        self._probe: dict = {}
        self._probe_lock = threading.Lock()
        self.helpers = None      # map mode: the imported harness modules (Helpers)
        self.tree_dirty = None   # map mode: whether the tree was dirty at the start; None = unknown

    def subst(self, text: str) -> str:
        return (text.replace("{python}", sys.executable).replace("{root}", self.root)
                .replace("{ruff_no_new}", self.ruff_no_new))

    def importable(self, module: str) -> bool:
        with self._probe_lock:
            if module not in self._probe:
                try:
                    proc = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=self.root,
                                          capture_output=True, timeout=120, check=False,
                                          stdin=subprocess.DEVNULL)
                    self._probe[module] = proc.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    self._probe[module] = False
            return self._probe[module]


def _which(tool: str) -> str | None:
    """The tool's absolute path: shutil.which resolves a relative PATH entry
    against this process's cwd, and the step runs in another one."""
    found = shutil.which(tool)
    if found is None and tool == "pwsh" and os.path.exists(WINDOWS_PWSH):
        found = WINDOWS_PWSH
    return os.path.abspath(found) if found else None


def _git_py_files(root: str) -> list:
    try:
        proc = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=root, capture_output=True,
                              timeout=60, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotStart(f"git ls-files failed: {exc}") from exc
    if proc.returncode != 0:
        raise CannotStart(f"git ls-files exit {proc.returncode}: "
                          f"{proc.stderr.decode(errors='replace').strip()}")
    # fsdecode: surrogateescape on POSIX, so a name that is not UTF-8 reaches the
    # child as its original bytes instead of raising here.
    return [os.fsdecode(p) for p in proc.stdout.split(b"\0") if p]


def build_argv(step: Step, ctx: Context) -> list:
    argv = []
    for arg in step.argv:
        if arg == "{git_py_files}":
            argv.extend(_git_py_files(ctx.root))
        else:
            argv.append(ctx.subst(arg))
    return argv


def preflight(step: Step, ctx: Context, argv: list):
    """(state, reason) when the step must not run, else None. Mutates argv[0]
    to the resolved tool path."""
    for need in step.needs:
        if need.startswith("path:"):
            path = ctx.subst(need[len("path:"):])
            full = path if os.path.isabs(path) else os.path.join(ctx.root, path)
            if not os.path.exists(full):
                return SKIP, f"NOT VERIFIED: {path} does not exist"
            continue
        if need.startswith("module:"):
            module = need[len("module:"):]
            if not ctx.importable(module):
                return SKIP, f"NOT VERIFIED: python module {module} is not importable"
            continue
        found = _which(need)
        if found is None:
            return SKIP, f"NOT VERIFIED: {need} not found on PATH"
        if argv and argv[0] == need:
            argv[0] = found
    if step.pytest:
        if not ctx.importable("pytest"):
            return CNT, "pytest not importable"
        if "-n" in step.argv and not ctx.importable("xdist"):
            return CNT, "pytest-xdist not importable (never run serially in its place)"
    return None


def _open_cwd(root: str, cwd: str):
    """(fd, path to start the child in) for a step cwd inside the root, or None.
    With /proc/self/fd (Linux) the checked directory is opened and the OPENED
    directory is checked again; the child starts in /proc/self/fd/<fd>, which it
    resolves through its own inherited copy of fd before exec (fd stays
    close-on-exec, so the step never holds it), so a swap of the pathname after
    this check cannot redirect it. Elsewhere fd is None and the path is the
    resolved one (a swap in between is not prevented there)."""
    real = contained_cwd(root, cwd)
    if real is None:
        return None
    if os.name == "nt" or not os.path.isdir("/proc/self/fd"):
        return None, real
    try:
        fd = os.open(real, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return None
    if not _inside(os.path.realpath(root), os.path.realpath(f"/proc/self/fd/{fd}")):
        os.close(fd)
        return None
    return fd, f"/proc/self/fd/{fd}"


def new_result(step: Step, ctx: Context) -> dict:
    return {"name": step.name, "phase": step.phase, "group": step.group, "argv": list(step.argv),
            "cwd": step.cwd, "timeout": step.timeout, "rc": None, "state": None, "reason": "",
            "seconds": 0.0, "log": os.path.join(ctx.out, "logs", f"{step.name}.log")}


def run_step(step: Step, ctx: Context) -> dict:
    res = new_result(step, ctx)
    if step.name in ctx.skip:  # before argv is built: a skipped step probes nothing
        res["state"], res["reason"] = SKIP, "skipped by --skip"
        return res
    if STOP.is_set():
        res["state"], res["reason"] = CNT, "runner stopped by a signal before this step started"
        return res
    try:
        argv = build_argv(step, ctx)
    except CannotStart as exc:
        res["state"], res["reason"] = CNT, f"could not start: {exc}"
        return res
    blocked = preflight(step, ctx, argv)
    res["argv"] = argv
    if blocked is not None:
        res["state"], res["reason"] = blocked
        return res
    # Resolved again at launch, not only when the table loaded: an earlier step
    # may have swapped a directory on this path for a symlink out of the root.
    # On Linux the child starts in the directory that was checked (_open_cwd).
    opened = _open_cwd(ctx.root, step.cwd)
    if opened is None:
        res["state"] = CNT
        res["reason"] = (f"could not start: cwd {step.cwd!r} resolves outside --root at launch "
                         "(symlinks resolved) or could not be opened")
        return res
    fd, cwd = opened
    started_at = time.monotonic()
    try:
        rc, timed_out, started, note = spawn_and_wait(argv, cwd, res["log"], step.timeout,
                                                      ctx.grace)
    finally:
        if fd is not None:
            os.close(fd)
    res["seconds"] = round(time.monotonic() - started_at, 1)
    res["rc"] = rc
    state, reason = classify(rc, timed_out, started)
    if note:
        reason = note
    if STOP.is_set() and state != PASS:
        state, reason = CNT, f"runner stopped by a signal while this step ran ({reason})"
    res["state"], res["reason"] = state, reason
    return res


def summary_line(res: dict) -> str:
    line = (f"{res['state']} {res['name']} rc={res['rc']} secs={res['seconds']} "
            f"log={res['log']}")
    return f"{line} -- {res['reason']}" if res["reason"] else line


# ---- inner: the heavy and solo phases, inside the one heavy-run call ------

def run_inner(part: str, steps: list, ctx: Context) -> int:
    # L-0517: the slot heavy-run says it gave this call; recorded, never trusted.
    data = {"started": time.time(), "pid": os.getpid(),
            "slot": os.environ.get("HEAVY_RUN_SLOT") or None, "steps": {}}
    lock = threading.Lock()
    write_status(part, data)

    def record(res: dict) -> None:
        with lock:
            data["steps"][res["name"]] = res
            write_status(part, data)
        print(summary_line(res), flush=True)

    def run_group(group: list) -> None:
        for step in group:
            record(run_step(step, ctx))

    threads = [threading.Thread(target=run_group, args=([s for s in steps if s.group == g],),
                                name=f"group-{g}") for g in ("A", "B")]
    for thread in threads:
        thread.start()
    while any(t.is_alive() for t in threads):
        for thread in threads:
            thread.join(timeout=0.5)
    run_group([s for s in steps if s.phase == "solo"])
    if STOP.is_set():
        return 128 + (STOP_SIGNAL[0] if STOP_SIGNAL else int(signal.SIGTERM))
    return 0


# ---- outer ----------------------------------------------------------------

RESULT_KEYS = ("name", "phase", "group", "argv", "cwd", "timeout", "rc", "state", "reason",
               "seconds", "log")


def _same_metadata(step: Step, res: dict) -> bool:
    """The row carries the table step's phase, group, cwd and timeout (a bool
    is never a timeout) and an argv list of strings -- every per-step field
    status.json must state (acceptance check 11). argv is only typed, not
    compared: build_argv adds the pinned pytest flags at launch."""
    argv, timeout = res["argv"], res["timeout"]
    return (res["phase"] == step.phase and res["group"] == step.group
            and res["cwd"] == step.cwd and not isinstance(timeout, bool)
            and type(timeout) is type(step.timeout) and timeout == step.timeout
            and isinstance(argv, list) and all(isinstance(a, str) for a in argv))


def _valid_result(step: Step, res) -> bool:
    """A heavy-part result is taken only when it is filed under its own name,
    carries its table step's metadata (_same_metadata), its rc is an int or
    null (never a bool or a string), and its state is the one the inner
    runner's classify() gives that rc: PASS needs rc 0, FAIL an rc classify()
    calls FAIL (never 77, a negative rc or a signal exit -- those are SKIP or
    COULD-NOT-TELL), SKIP rc 77 or null (--skip, a missing tool) -- a PASS
    without the exit status that proves it, or a SKIP or FAIL over an exit
    that says otherwise, is never taken (T-0082). COULD-NOT-TELL takes any rc:
    it never passes. Anything else is dropped, and the step reads
    COULD-NOT-TELL."""
    if not isinstance(res, dict) or not all(k in res for k in RESULT_KEYS):
        return False
    rc, state = res["rc"], res["state"]
    if res["name"] != step.name or state not in (PASS, FAIL, SKIP, CNT):
        return False
    if not _same_metadata(step, res):
        return False
    if rc is not None and (isinstance(rc, bool) or not isinstance(rc, int)):
        return False
    if state == PASS:
        return rc == 0
    if state == FAIL:
        return rc is not None and classify(rc, False, True)[0] == FAIL
    if state == SKIP:
        return rc is None or rc == EXIT_SKIP
    return True


def _slot(value):
    """A heavy-run slot name (a lock file basename) or None: a non-empty string
    of at most 64 characters with no `/`. Anything else is unknown (L-0517)."""
    if isinstance(value, str) and value and len(value) <= 64 and "/" not in value:
        return value
    return None


def _part(got, table: dict):
    """(steps, started, slot) from heavy-part.json as read: only well-formed
    results for a step of `table` (name -> Step), `started` only when a finite
    non-bool number, and `slot` only when _slot() accepts it. A document of any
    other shape gives ({}, None, None), never an exception."""
    if not isinstance(got, dict):
        return {}, None, None
    steps = got.get("steps")
    steps = {n: r for n, r in steps.items()
             if isinstance(n, str) and n in table and _valid_result(table[n], r)} \
        if isinstance(steps, dict) else {}
    started = got.get("started")
    if isinstance(started, bool) or not isinstance(started, (int, float)) \
            or not math.isfinite(started):
        started = None
    return steps, started, _slot(got.get("slot"))


def resolve_heavy_run(env) -> tuple:
    value = env.get("HEAVY_RUN")
    if value in (None, ""):
        if os.path.isfile(DEFAULT_HEAVY_RUN) and os.access(DEFAULT_HEAVY_RUN, os.X_OK):
            return "present", DEFAULT_HEAVY_RUN
        return "absent", None
    if value == "none":
        return "absent", None
    if os.path.isfile(value) and os.access(value, os.X_OK):
        return "present", os.path.abspath(value)
    raise Refusal(f"HEAVY_RUN={value} is not executable (unset it, or set HEAVY_RUN=none to run "
                  "the heavy phase directly)")


def _git(root: str, *args: str):
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=60,
                              check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    # surrogateescape cannot raise: a file name that is not UTF-8 in
    # `status --porcelain` must not crash the runner before status.json exists.
    return proc.stdout.decode("utf-8", "surrogateescape") if proc.returncode == 0 else None


def heavy_run_label(hr: dict) -> str:
    return hr["path"] if hr["mode"] == "present" else "absent (uncapped)"


def heavy_budget(steps: list, grace: float) -> float:
    a = sum(s.timeout for s in steps if s.group == "A")
    b = sum(s.timeout for s in steps if s.group == "B")
    solo = sum(s.timeout for s in steps if s.phase == "solo")
    return max(a, b) + solo + grace * (len(steps) + 2) + SLOT_WAIT_ALLOWANCE


def _log_tail(path: str) -> str:
    """The last non-empty line of a log, for a reason string ('' if none)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    lines = [ln.strip() for ln in lines if ln.strip()]
    return lines[-1][:300] if lines else ""


def run_outer(args, steps: list, source: str, ctx: Context, hr: dict, digest: str) -> int:
    status_path = os.path.join(ctx.out, "status.json")
    head = _git(ctx.root, "rev-parse", "HEAD")
    porcelain = _git(ctx.root, "status", "--porcelain")
    status = {
        "runner": "scripts/gate-runner.py",
        "root": ctx.root,
        "head": head.strip() if head else None,
        "dirty": (porcelain.strip() != "") if porcelain is not None else None,
        "table_source": source,
        "only": args.only or None,
        "heavy_run": hr,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ended": None,
        "overall": "RUNNING",
        "steps": [],
    }
    results = status["steps"]

    def save() -> None:
        write_status(status_path, status)

    print(f"gate-runner: root {ctx.root}  heavy_run: {heavy_run_label(hr)}  status: {status_path}",
          flush=True)
    save()
    for step in [s for s in steps if s.phase == "cheap"]:
        res = run_step(step, ctx)
        results.append(res)
        save()
        print(summary_line(res), flush=True)

    inner_steps = [s for s in steps if s.phase in ("heavy", "solo")]
    if inner_steps:
        part = os.path.join(ctx.out, "heavy-part.json")
        cmd = [sys.executable, os.path.abspath(__file__), "--inner", part, "--root", ctx.root,
               "--out", ctx.out, "--grace", f"{ctx.grace:g}", "--table-digest", digest]
        if source != "builtin":
            cmd += ["--table", source]
        for name in args.skip or ():
            cmd += ["--skip", name]
        for name in args.only or ():
            cmd += ["--only", name]
        if hr["mode"] == "present":
            cmd = [hr["path"], *cmd]
        printed: set = set()
        wanted = {s.name: s for s in inner_steps}  # a result for any other name is never taken
        slot: dict = {}  # step name -> its index in results, once recorded

        def take(name: str, res: dict) -> None:
            if name in slot:
                results[slot[name]] = res
            else:
                slot[name] = len(results)
                results.append(res)

        def tick() -> None:
            # Copy each heavy result into status.json as soon as heavy-part.json
            # has it, so an outer runner killed mid-call loses none of them.
            fresh = [(n, r) for n, r in _part(read_json(part), wanted)[0].items()
                     if n not in printed]
            for name, res in fresh:
                printed.add(name)
                take(name, res)
                print(summary_line(res), flush=True)
            if fresh:
                save()

        budget = args.heavy_timeout or heavy_budget(inner_steps, ctx.grace)
        launched = time.time()
        hr["launched"] = True
        save()
        if STOP.is_set():
            rc, timed_out, note = None, False, "runner stopped by a signal before the heavy-run call"
        else:
            rc, timed_out, _started, note = spawn_and_wait(
                cmd, ctx.root, os.path.join(ctx.out, "logs", "heavy-run.log"), budget,
                ctx.grace * 2 + 5, on_tick=tick)
        hr["rc"] = rc
        recorded, inner_started, hr["slot"] = _part(read_json(part), wanted)
        if inner_started is not None:
            hr["waited_seconds"] = round(inner_started - launched, 1)
        why = (f"heavy-run call timed out after {budget:g}s (slot wait included)" if timed_out
               else note or f"heavy-run call ended rc={rc}")
        if rc == EXIT_USAGE and not timed_out and not note:
            # The inner runner refused (e.g. the table changed): say why.
            tail = _log_tail(os.path.join(ctx.out, "logs", "heavy-run.log"))
            if tail:
                why = f"{why} ({tail})"
        for step in inner_steps:
            res = recorded.get(step.name)
            if res is None:
                res = new_result(step, ctx)
                res["state"] = CNT
                res["reason"] = f"{why} before this step recorded a result"
            take(step.name, res)
            if step.name not in printed:
                printed.add(step.name)
                print(summary_line(res), flush=True)

    state, code = overall(results)
    status["overall"] = state
    status["ended"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save()
    print(f"overall: {state}  heavy_run: {heavy_run_label(hr)}  status: {status_path}")
    print(last_line(results, source, args.only))
    return code


def last_line(results: list, source: str, only) -> str:
    notes = []
    skipped = [r["name"] for r in results if r["state"] == SKIP]
    if skipped:
        notes.append(f"{len(skipped)} SKIPPED (NOT VERIFIED): {', '.join(skipped)}")
    if source != "builtin":
        notes.append(f"table {source}: not the repo gate")
    if only:
        notes.append("subset (--only): not the repo gate")
    if not notes:
        notes.append(f"all {len(results)} steps of the repo gate ran; none SKIPPED")
    return "; ".join(notes)


def default_out(root: str) -> str:
    head = _git(root, "rev-parse", "--short=12", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = os.path.join(tempfile.gettempdir(), "gate-runner", f"{(head or 'nogit').strip()}-{stamp}")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    out, n = base, 1
    while True:  # mkdir is the claim: two runs in one second never share a directory
        try:
            os.mkdir(out)
            return out
        except FileExistsError:
            n += 1
            out = f"{base}-{n}"


# ---- CI drift ---------------------------------------------------------------

_ASSIGN = re.compile(r"""^[A-Za-z_][A-Za-z0-9_]*=("[^"]*"|'[^']*'|\S*)$""")
_LEAD_KEYWORDS = ("if", "elif", "then", "else", "while", "until", "do", "!")
_END_KEYWORDS = ("fi", "done")
_NO_OPS = (":", "true", "false")


def normalise(cmd: str) -> str:
    return " ".join(cmd.split())


def _split_simple(line: str) -> list:
    """Split one shell line on `;`, `&&`, `||` and `|` outside quotes and
    outside `$(...)`, keeping each part's original text."""
    parts, buf, quote, depth, i = [], [], None, 0, 0
    while i < len(line):
        ch, two = line[i], line[i:i + 2]
        if quote:
            if ch == "\\" and quote == '"':
                buf.append(line[i:i + 2])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif two == "$(":
            depth += 1
            buf.append(two)
            i += 2
            continue
        elif ch == ")" and depth:
            depth -= 1
        elif depth == 0 and two in ("&&", "||"):
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        elif depth == 0 and ch in (";", "|"):
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _simple_command(part: str):
    """The command a split part runs, or None for shell syntax that runs no
    check: keywords alone, `[ ... ]`/`test` conditions, no-ops, `for` headers,
    `echo`, bare assignments."""
    words = part.split()
    while words and words[0] in _LEAD_KEYWORDS:
        words = words[1:]
    if not words or words[0] in _END_KEYWORDS or words[0] in _NO_OPS or words[0] == "for":
        return None
    if words[0] in ("[", "[[", "test", "echo", "exit"):
        return None
    cmd = " ".join(words)
    return None if _ASSIGN.match(cmd) else cmd


def _close(text: str, i: int) -> int:
    """Index just past the `)` that closes the `(` before i: quote-aware and
    nesting-aware; len(text) when unclosed."""
    depth, quote = 1, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "\\":
            i += 2
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def substitutions(text: str) -> list:
    """The bodies of every command substitution in `text` that the shell would
    run: `$(...)`, backticks, `<(...)` and `>(...)`, outside single quotes
    (inside double quotes they still run). `$((...))` is arithmetic, not a
    command; substitutions inside it are still returned. Nested bodies are
    returned whole; split_commands recurses into them."""
    out, quote, i = [], None, 0
    while i < len(text):
        ch, two = text[i], text[i:i + 2]
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            quote = None if quote == '"' else '"'
            i += 1
            continue
        if quote is None and ch == "'":
            quote = "'"
            i += 1
            continue
        if text[i:i + 3] == "$((":
            end = _close(text, i + 2)
            out += substitutions(text[i + 3:end - 1])
            i = end
            continue
        if two in ("$(", "<(", ">("):
            end = _close(text, i + 2)
            out.append(text[i + 2:end - 1])
            i = end
            continue
        if ch == "`":
            end = text.find("`", i + 1)
            end = len(text) if end < 0 else end
            out.append(text[i + 1:end])
            i = end + 1
            continue
        i += 1
    return out


def split_commands(run: str) -> list:
    """Every simple command in a `run:` block. A line is split on `;`, `&&`,
    `||` and `|` (quote- and `$(...)`-aware), so a check chained onto an
    install, an echo or a condition, or written as a one-line `if`/`while`/
    `for` body, is still a command. Dropped: blank and comment lines, shell
    keywords, `[ ]`/`test` conditions, no-ops, `echo`, `exit` and bare
    variable assignments -- but a dropped part is first searched for command
    substitutions (`$(...)`, backticks, `<(...)`), and each body is split the
    same way, so `echo "$(python3 x.py)"` still counts `python3 x.py`."""
    out = []
    for raw in run.replace("\\\n", " ").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for part in _split_simple(line):
            cmd = _simple_command(part)
            if cmd is not None:
                out.append(normalise(cmd))
                continue
            for body in substitutions(part):
                out += split_commands(body)
    return out


def _excluded(workflow: str, cmd: str) -> bool:
    """A wildcard covers one simple command only: its tail may not run another
    command through any substitution -- `$(...)`, backticks, `<(...)` or
    `>(...)` (substitutions() is the one definition of what runs)."""
    for wf, pattern, _reason in EXCLUDED_CI:
        if wf != workflow:
            continue
        pattern = normalise(pattern)
        if pattern.endswith("*") and cmd.startswith(pattern[:-1]):
            tail = cmd[len(pattern) - 1:]
            if not substitutions(tail):
                return True
        if cmd == pattern:
            return True
    return False


def ci_drift(root: str, table=TABLE) -> list:
    """Problems, one string each; [] when the table covers PR-path CI."""
    import yaml
    wfdir = os.path.join(root, ".github", "workflows")
    try:
        present = sorted(f for f in os.listdir(wfdir) if f.endswith((".yml", ".yaml")))
    except OSError as exc:
        return [f"cannot read {wfdir}: {exc}"]
    excluded = {f for f, _ in EXCLUDED_WORKFLOWS}
    problems = [f"{f}: workflow is neither in INCLUDED_WORKFLOWS nor EXCLUDED_WORKFLOWS"
                for f in present if f not in INCLUDED_WORKFLOWS and f not in excluded]
    problems += [f"{f}: in INCLUDED_WORKFLOWS but not in .github/workflows/"
                 for f in INCLUDED_WORKFLOWS if f not in present]
    covered = {(wf, normalise(cmd)) for step in table for wf, cmd in step.ci}
    windows_only = {cond for cond, _ in WINDOWS_ONLY_IFS}
    for wf in INCLUDED_WORKFLOWS:
        if wf not in present:
            continue
        try:
            with open(os.path.join(wfdir, wf), encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            problems.append(f"{wf}: cannot parse: {exc}")
            continue
        problems += _workflow_commands(wf, doc, covered, windows_only)
    return problems


def _workflow_commands(wf: str, doc, covered: set, windows_only: set) -> list:
    """Drift problems for one parsed workflow. Valid YAML of the wrong shape at
    any level (no `jobs` mapping, a job, `steps`, a step or a `run` of the
    wrong type) is itself a problem naming where: the check never reads a
    workflow it cannot walk as "nothing to check", and never raises."""
    if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), dict):
        return [f"{wf}: cannot check: the document has no `jobs` mapping"]
    problems = []
    for job_id, job in doc["jobs"].items():
        if not isinstance(job, dict):
            problems.append(f"{wf} jobs.{job_id}: cannot check: the job is not a mapping")
            continue
        steps = job.get("steps")
        if steps is None:  # a reusable-workflow call (`uses:`) has no steps
            continue
        if not isinstance(steps, list):
            problems.append(f"{wf} jobs.{job_id}: cannot check: `steps` is not a list")
            continue
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                problems.append(f"{wf} jobs.{job_id}.steps[{i}]: cannot check: not a mapping")
                continue
            run = step.get("run")
            if run is None or normalise(str(step.get("if", ""))) in windows_only:
                continue
            if not isinstance(run, str):
                problems.append(f"{wf} jobs.{job_id}.steps[{i}]: cannot check: `run` is not text")
                continue
            for cmd in split_commands(run):
                if (wf, cmd) not in covered and not _excluded(wf, cmd):
                    problems.append(f"{wf} jobs.{job_id}: `{cmd}` is in neither the step "
                                    "table nor EXCLUDED_CI")
    return problems


# ---- map mode (R-80): tiers and slices of .crew/verify.json ----------------

MAP_SCRIPTS = os.path.join("plugin", "crew", "hooks", "scripts")
TIMINGS_FILE = os.path.join(".crew", ".verify-gate.timings.json")
DEFAULT_FAST_SECONDS = 120
UNKNOWN_SECONDS = 300
MAX_SLICES = 64
GIB = 1024 ** 3
SYNTHETIC = ("@always", "@default", "@unmapped")
NOT_VERIFIED_HEAVY = "NOT VERIFIED - heavy, runs at Gate"
NOT_VERIFIED_FAST = "NOT VERIFIED - fast, runs per round"


@dataclass
class Helpers:
    """The read-only harness modules map mode imports (D2, D3). None = not
    importable; every use below says what an absent one means."""
    vr: object = None
    ca: object = None
    notices: list = dataclasses.field(default_factory=list)


def load_helpers(root: str) -> Helpers:
    """Import verify_record and completion_audit from the root's own
    plugin/crew/hooks/scripts. The directory stays on sys.path for the process
    (completion_audit imports a sibling lazily, inside its call)."""
    scripts = os.path.join(root, MAP_SCRIPTS)
    helpers = Helpers()
    if os.path.isdir(scripts) and scripts not in sys.path:
        sys.path.insert(0, scripts)
    for attr, name in (("vr", "verify_record"), ("ca", "completion_audit")):
        try:
            if not os.path.isdir(scripts):
                raise ImportError(f"{scripts} does not exist")
            setattr(helpers, attr, __import__(name))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            helpers.notices.append(f"gate-runner map: {name} is not importable "
                                   f"({type(exc).__name__}: {exc})" + (
                                       " - every changed path is judged (none is bookkeeping or "
                                       "an artifact)" if name == "completion_audit" else ""))
    return helpers


def matches(path: str, pat: str) -> bool:
    """verify-gate.sh's `def matches`, verbatim in behaviour (test 12 execs the
    original and compares): fnmatch's * spans '/', so the '**/'-stripped form
    and the '/**/' -> '/' form are tried as well."""
    import fnmatch
    cands = {pat}
    if pat.startswith("**/"):
        cands.add(pat[3:])
    cands.add(pat.replace("/**/", "/"))
    return any(fnmatch.fnmatch(path, c) for c in cands)


def load_map(path: str, root: str):
    """(cfg, sha256 of the file's bytes). Refuses (D18) when any rule, selected
    or not, has no usable unique `id`, or is not shaped as a rule; the message
    names every offending rules[i]."""
    full = path if os.path.isabs(path) else os.path.join(root, path)
    try:
        with open(full, "rb") as fh:
            raw = fh.read()
        cfg = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise Refusal(f"--map {path}: not readable JSON ({exc})") from exc
    if not isinstance(cfg, dict):
        raise Refusal(f"--map {path}: expected a JSON object")
    rules = cfg.get("rules", [])
    if not isinstance(rules, list):
        raise Refusal(f"--map {path}: `rules` is not a list")
    seen: dict = {}
    for i, rule in enumerate(rules):
        if isinstance(rule, dict) and isinstance(rule.get("id"), str) and rule["id"]:
            seen.setdefault(rule["id"], []).append(i)
    bad = []
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            bad.append(f"rules[{i}]: not an object")
            continue
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid:
            bad.append(f"rules[{i}]: no `id`, or an `id` that is not a non-empty string")
        elif rid.startswith("@"):
            bad.append(f"rules[{i}]: id {rid!r} begins with '@' (reserved for synthetic units)")
        elif len(seen[rid]) > 1:
            other = next(j for j in seen[rid] if j != i)
            bad.append(f"rules[{i}]: id {rid!r} is also used by rules[{other}]")
        paths, run = rule.get("paths"), rule.get("run")
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            bad.append(f"rules[{i}]: `paths` must be a list of strings")
        if not isinstance(run, list) or not all(isinstance(c, str) for c in run):
            bad.append(f"rules[{i}]: `run` must be a list of strings")
    if bad:
        raise Refusal("--map: " + "; ".join(bad) + " (no positional fallback: nothing run)")
    return cfg, hashlib.sha256(raw).hexdigest()


def _commands(rule: dict) -> list:
    return [c for c in rule.get("run", []) if isinstance(c, str) and c.strip()]


def _rule_env(rule: dict) -> dict:
    env = rule.get("env")
    if not isinstance(env, dict):
        return {}
    return {k: v for k, v in env.items() if isinstance(k, str) and isinstance(v, str)}


def _identity(cmd: str, env: dict) -> str:
    """verify-gate's command identity: the text, plus the canonical env JSON
    after a \\x1c when the rule declares an env."""
    if not env:
        return cmd
    return cmd + "\x1c" + json.dumps(env, sort_keys=True, separators=(",", ":"))


def declared_seconds(rule: dict):
    secs = rule.get("seconds")
    if isinstance(secs, bool) or not isinstance(secs, (int, float)) or not math.isfinite(secs) \
            or secs < 0:
        return None
    return secs


def reach_exclusion(cmds_or_rule, helpers: Helpers, root: str, declared=True):
    """(kind, reason) when a rule's or command list's reach keeps it from
    running, else None. Mirrors verify-gate's `_classify_run_reach` (all three
    non-local scan_reach statuses exclude; verify_record unimportable = wrapper)
    and its declared-reach branch (D10)."""
    if declared:
        rule = cmds_or_rule
        reach = rule.get("reach")
        if isinstance(reach, str) and reach != "local":
            return "reach_declared", f"declared reach: {reach}"
        if reach is not None:
            return None
        run = rule.get("run")
    else:
        run = cmds_or_rule
    if helpers.vr is None:
        status, detail = "wrapper", "the shared scanner (verify_record.py) is not importable"
    else:
        status, detail = helpers.vr.scan_reach(run, root)
    if status == "verb":
        return "reach_undeclared", f"remote verb {detail!r}"
    if status == "syntax":
        return "reach_syntax", "shell syntax in an undeclared rule"
    if status == "wrapper":
        return "reach_wrapper", f"wrapper or inline shell ({detail})"
    return None


def select_rules(cfg: dict, changed: list, root: str, helpers: Helpers) -> dict:
    """Which rules the map requires for `changed` (D2): bookkeeping paths are
    removed from the set; a path is a hit when any rule's pattern matches it,
    before reach exclusion; an unmatched path is unmapped unless it is a refresh
    artifact. Returns {"changed", "matched" (rule indices, file order),
    "unmapped", "notices"}."""
    notices: list = []
    kept = list(changed)
    kinds: dict = {}
    if helpers.ca is not None:
        try:
            kinds = dict(zip(changed, helpers.ca.classify_paths(root, changed)))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            notices.append("gate-runner map: could not tell bookkeeping and refresh artifacts from "
                           f"other changes ({type(exc).__name__}: {exc}) - every changed path is judged")
    kept = [f for f in changed if kinds.get(f) != "bookkeeping"]
    rules = cfg.get("rules", []) or []
    matched, unmapped = [], []
    for path in kept:
        hit = False
        for ri, rule in enumerate(rules):
            if any(matches(path, p) for p in rule["paths"]):
                hit = True
                if ri not in matched:
                    matched.append(ri)
        if not hit and kinds.get(path) != "artifact":
            unmapped.append(path)
    return {"changed": kept, "matched": sorted(matched), "unmapped": unmapped, "notices": notices}


def read_timings(root: str):
    """({rule_key: seconds}, notice or None). A missing cache and a present one
    of the wrong shape both give every rule heavy and one notice (D4)."""
    path = os.path.join(root, TIMINGS_FILE)
    if not os.path.exists(path):
        return {}, f"gate-runner map: {TIMINGS_FILE} is missing - every rule is heavy"
    data = read_json(path)
    if isinstance(data, dict) and isinstance(data.get("rules"), dict):
        return data["rules"], None
    return {}, f"gate-runner map: {TIMINGS_FILE} is unreadable or the wrong shape - every rule is heavy"


def _measured(timings: dict, key):
    value = timings.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def classify_tier(unit: dict, rules: list, timings: dict, helpers: Helpers,
                  fast_seconds: float) -> None:
    """Set unit["tier"] and unit["tier_basis"] (D4): fast only when every
    member rule has a measurement on this machine below fast_seconds. Declared
    seconds alone, no scanner to key the cache, and the synthetic units are
    heavy."""
    if unit["kind"] != "rule":
        unit["tier"], unit["tier_basis"] = "heavy", "synthetic unit has no timing key"
        return
    if helpers.vr is None:
        unit["tier"], unit["tier_basis"] = "heavy", "verify_record not importable: no timing key"
        return
    worst = 0
    for ri in unit["members"]:
        measured = _measured(timings, helpers.vr.rule_key(rules[ri]))
        if measured is None:
            decl = declared_seconds(rules[ri])
            unit["tier"] = "heavy"
            unit["tier_basis"] = (f"declared {decl:g}s, platform not stated" if decl is not None
                                  else "no measurement on this machine")
            return
        worst = max(worst, measured)
    unit["tier"] = "fast" if worst < fast_seconds else "heavy"
    unit["tier_basis"] = f"measured {worst}s on this machine (fast below {fast_seconds:g}s)"


def _cmd_timeout(rule: dict) -> int:
    decl = declared_seconds(rule)
    return int(max(300, 3 * (decl if decl is not None else UNKNOWN_SECONDS)))


def _member(rid: str, idx, rule, cmds: list, exclusion, credit_to=None) -> dict:
    return {"id": rid, "idx": idx, "commands": cmds, "env": _rule_env(rule) if rule else {},
            "timeout": _cmd_timeout(rule) if rule else 300, "exclusion": exclusion,
            "requires_clean_tree": bool(rule and rule.get("requiresCleanTree") is True),
            "credit_to": credit_to, "fail_paths": None}


def build_units(cfg: dict, sel: dict, root: str, helpers: Helpers) -> list:
    """The units of the selected set (D6-D9): one per matched rule, except a
    rule credited under a valid coveredBy joins its superset's unit; plus the
    synthetic @always, @default and @unmapped units. Nothing here reads the
    timings cache, the tree's cleanliness or the environment."""
    rules = cfg.get("rules", []) or []
    matched = sel["matched"]
    rule_cmds, cmds, env_of = {}, [], {}
    for ri in matched:
        env = _rule_env(rules[ri])
        env_of[ri] = env
        rule_cmds[ri] = []
        for c in _commands(rules[ri]):
            ident = _identity(c, env)
            if ident not in cmds:
                cmds.append(ident)
            if ident not in rule_cmds[ri]:
                rule_cmds[ri].append(ident)
    always = [c for c in (cfg.get("always") or []) if isinstance(c, str) and c.strip()]
    joined: dict = {}  # subset rule index -> superset rule index
    if helpers.vr is not None:
        valid, _notices = helpers.vr.cover_declarations(rules)
        order, guards, _n = helpers.vr.cover_plan(rules, matched, rule_cmds, cmds, always, {})
        guard_of = dict(zip(order, guards))
        for ri, sup in valid.items():
            if ri not in rule_cmds or not rule_cmds[ri]:
                continue
            if all(guard_of.get(c) is not None and guard_of[c]["rules"] == [sup]
                   for c in rule_cmds[ri]):
                joined[ri] = sup
    units = []
    for ri in matched:
        if ri in joined:
            continue
        rule = rules[ri]
        members = [ri] + sorted(s for s, sup in joined.items() if sup == ri)
        specs = []
        for mi in members:
            r = rules[mi]
            specs.append(_member(r["id"], mi, r, _commands(r), reach_exclusion(r, helpers, root),
                                 credit_to=rule["id"] if mi != ri else None))
        decl = declared_seconds(rule)
        units.append({"id": rule["id"], "kind": "rule", "members": members,
                      "rules": [rules[m]["id"] for m in members],
                      "cost": decl if decl is not None else UNKNOWN_SECONDS,
                      "cost_basis": "declared" if decl is not None else
                      f"seconds missing: {UNKNOWN_SECONDS}",
                      "specs": specs,
                      "timeout": sum(len(s["commands"]) * s["timeout"] for s in specs)})
    # @always: its commands are reach-classified one by one (verify-gate :2276-2282).
    survivors_always = 0
    if always:
        cmds_a = []
        for c in always:
            excl = reach_exclusion([c], helpers, root, declared=False)
            cmds_a.append({"cmd": c, "exclusion": list(excl) if excl else None})
            survivors_always += excl is None
        spec = _member("@always", None, None, always, None)
        spec["commands"] = [x["cmd"] for x in cmds_a]
        spec["command_exclusions"] = [x["exclusion"] for x in cmds_a]
        units.append(_synthetic("@always", [spec]))
    # @default exists exactly when nothing is left to run (verify-gate.sh:2285);
    # requiresCleanTree does not count as exclusion for this decision (D9).
    contributes = any(reach_exclusion(rules[ri], helpers, root) is None and _commands(rules[ri])
                      for ri in matched)
    default = [c for c in (cfg.get("default") or []) if isinstance(c, str) and c.strip()]
    if not contributes and not survivors_always and default:
        cmds_d = [(c, reach_exclusion([c], helpers, root, declared=False)) for c in default]
        spec = _member("@default", None, None, default, None)
        spec["command_exclusions"] = [list(e) if e else None for _c, e in cmds_d]
        units.append(_synthetic("@default", [spec]))
    return units


def _synthetic(uid: str, specs: list) -> dict:
    return {"id": uid, "kind": "synthetic", "members": [], "rules": [uid], "cost": 0,
            "cost_basis": "synthetic", "specs": specs,
            "timeout": sum(len(s["commands"]) * s["timeout"] for s in specs)}


def unmapped_policy(cfg: dict, unmapped: list):
    """(unit or None, notice or None) for D9's `unmapped` handling. The key is
    read parsed; an unknown value fails closed (a recorded divergence from
    verify-gate.sh:3506, which greps the literal "fail")."""
    if not unmapped:
        return None, None
    if "unmapped" not in cfg:
        return None, "gate-runner map: `unmapped` is not set - unmapped paths do not fail: " + \
            ", ".join(unmapped)
    value = cfg["unmapped"]
    if value == "ignore":
        return None, None
    if value == "warn":
        return None, "gate-runner map: unmapped paths (unmapped=warn): " + ", ".join(unmapped)
    spec = _member("@unmapped", None, None, [], None)
    spec["fail_paths"] = list(unmapped)
    spec["fail_value"] = value
    return _synthetic("@unmapped", [spec]), None


def partition(units: list, n: int) -> dict:
    """{unit id: slice number 1..n} (D7). Real units sorted by (-cost, id),
    each to the slice with the smallest total, ties to the lowest index;
    synthetic units are always slice 1 and weigh nothing."""
    totals = [0.0] * n
    out = {}
    for unit in units:
        if unit["kind"] == "synthetic":
            out[unit["id"]] = 1
    for unit in sorted((u for u in units if u["kind"] == "rule"),
                       key=lambda u: (-u["cost"], u["id"])):
        k = min(range(n), key=lambda i: (totals[i], i))
        totals[k] += unit["cost"]
        out[unit["id"]] = k + 1
    return out


def partition_digest(units: list, assignment: dict, n: int) -> str:
    rows = sorted([u["id"], assignment[u["id"]], sorted(u["rules"])] for u in units)
    text = json.dumps({"n": n, "units": rows}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def probe_workers(meminfo: str = "/proc/meminfo", cpus=None, probe_cpus=True):
    """(workers, source, why) (D16): max(1, min(cpus, MemAvailable // 1.5 GiB,
    4)); any failure to know is the smallest value, said out loud."""
    try:
        with open(meminfo, encoding="utf-8") as fh:
            text = fh.read()
        match = re.search(r"^MemAvailable:\s+(\d+)\s*kB", text, re.M)
        if not match:
            raise ValueError("no MemAvailable line")
        avail = int(match.group(1)) * 1024
        count = os.cpu_count() if cpus is None and probe_cpus else cpus
        if not count:
            raise ValueError("cpu count unknown")
    except (OSError, ValueError) as exc:
        return 1, "fallback", f"probe failed: {exc}; conservative fallback"
    return max(1, min(count, int(avail // (1.5 * GIB)), 4)), "probe", \
        f"{count} cpus, {avail // GIB} GiB available"


def parse_slice(text: str):
    match = re.fullmatch(r"(\d+)/(\d+)", text or "")
    if not match:
        raise Refusal(f"--slice {text!r}: expected k/n with whole numbers")
    k, n = int(match.group(1)), int(match.group(2))
    if not 1 <= n <= MAX_SLICES or not 1 <= k <= n:
        raise Refusal(f"--slice {text}: need 1 <= k <= n <= {MAX_SLICES}")
    return k, n


def changed_set(args, root: str) -> list:
    """The changed paths (D13): a file (or - for stdin), or the diff against a
    base ref plus every dirty path."""
    if args.changed_file:
        try:
            if args.changed_file == "-":
                raw = sys.stdin.buffer.read()
            else:
                with open(args.changed_file, "rb") as fh:
                    raw = fh.read()
        except OSError as exc:
            raise Refusal(f"--changed-file {args.changed_file}: {exc}") from exc
        # surrogateescape: a name that is not UTF-8 survives; only the line
        # terminator is removed, never other whitespace a name may contain.
        text = raw.decode("utf-8", "surrogateescape")
        lines = [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]
        return [ln for ln in lines if ln]
    diff = _git(root, "-c", "core.quotePath=false", "diff", "--name-only", "-z",
                f"{args.base}...HEAD")
    status = _git(root, "-c", "core.quotePath=false", "status", "--porcelain", "-z")
    if diff is None or status is None:
        raise Refusal(f"--base {args.base}: git could not list the changed files")
    paths = [p for p in diff.split("\0") if p]
    toks = [t for t in status.split("\0") if t]
    i = 0
    while i < len(toks):
        tok = toks[i]
        paths.append(tok[3:])
        if tok[:1] in "RC" or tok[1:2] in "RC":
            i += 1
            if i < len(toks):
                paths.append(toks[i])
        i += 1
    return paths


def build_plan(args, root: str) -> dict:
    """Everything map mode decides before anything runs; pure of the run."""
    helpers = load_helpers(root)
    cfg, map_sha = load_map(args.map, root)
    changed = changed_set(args, root)
    # NUL-joined: a path can hold a newline but never a NUL, so no two sets collide.
    changed_digest = hashlib.sha256(
        "\0".join(sorted(set(changed))).encode("utf-8", "surrogateescape")).hexdigest()
    sel = select_rules(cfg, changed, root, helpers)
    rules = cfg.get("rules", []) or []
    units = build_units(cfg, sel, root, helpers)
    um_unit, um_notice = unmapped_policy(cfg, sel["unmapped"])
    if um_unit:
        units.append(um_unit)
    timings, tnote = read_timings(root)
    for unit in units:
        classify_tier(unit, rules, timings, helpers, args.fast_seconds)
    slice_k, n = (parse_slice(args.slice) if args.slice else (None, 1))
    assignment = partition(units, n)
    for unit in units:
        unit["slice"] = assignment[unit["id"]]
    notices = helpers.notices + sel["notices"] + ([tnote] if tnote else []) + \
        ([um_notice] if um_notice else [])
    tier = "all" if args.slice else (args.tier or "all")
    # Disposition of every matched rule: exactly one of run, other_tier, excluded (test 2).
    other, dispositions = [], {}
    run_units = []
    for unit in units:
        if unit["id"] == "@unmapped":
            if slice_k is None or unit["slice"] == slice_k:
                run_units.append(unit)
            continue
        if slice_k is not None and unit["slice"] != slice_k:
            continue
        if slice_k is None and tier != "all" and unit["tier"] != tier:
            why = NOT_VERIFIED_HEAVY if unit["tier"] == "heavy" else NOT_VERIFIED_FAST
            for rid in unit["rules"]:
                other.append({"id": rid, "unit": unit["id"], "state": SKIP, "reason": why,
                              "tier": unit["tier"]})
                dispositions[rid] = "other_tier"
            continue
        run_units.append(unit)
        for spec in unit["specs"]:
            dispositions[spec["id"]] = f"excluded:{spec['exclusion'][0]}" if spec["exclusion"] \
                else "run"
    carried = []
    if cfg.get("preReview"):
        carried.append({"id": "preReview", "reason": "run by review_run.py before a review "
                        "round; not run here"})
    head = _git(root, "rev-parse", "HEAD")
    return {"helpers": helpers, "rules": rules, "units": units, "run_units": run_units,
            "other_tier": other, "carried": carried, "dispositions": dispositions,
            "notices": notices, "matched": [rules[i]["id"] for i in sel["matched"]],
            "unmapped": sel["unmapped"], "tier": tier, "slice_k": slice_k, "n": n,
            "head": head.strip() if head else None, "changed_digest": changed_digest,
            "map_digest": map_sha,
            "partition_digest": partition_digest(units, assignment, n)}


def plan_json(plan: dict) -> dict:
    return {
        "mode": f"slice {plan['slice_k']}/{plan['n']}" if plan["slice_k"] else f"tier {plan['tier']}",
        "head": plan["head"], "changed_digest": plan["changed_digest"],
        "map_digest": plan["map_digest"], "partition_digest": plan["partition_digest"],
        "matched": plan["matched"], "unmapped": plan["unmapped"],
        "units": [{"id": u["id"], "kind": u["kind"], "rules": u["rules"], "slice": u["slice"],
                   "tier": u["tier"], "tier_basis": u["tier_basis"], "cost": u["cost"],
                   "cost_basis": u["cost_basis"],
                   "run_here": u in plan["run_units"]} for u in plan["units"]],
        "dispositions": plan["dispositions"], "other_tier": plan["other_tier"],
        "carried": plan["carried"], "notices": plan["notices"],
    }


# ---- map mode: running a unit -------------------------------------------

def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _record(rid: str, unit: str) -> dict:
    return {"id": rid, "unit": unit, "state": None, "reason": "", "rc": None, "seconds": 0.0,
            "credited_by": None, "commands": []}


def _run_command(cmd: str, env_extra: dict, timeout: int, log: str, ctx: Context) -> dict:
    out = {"cmd": cmd, "rc": None, "state": CNT, "reason": "", "log": log, "seconds": 0.0}
    bash = _which("bash")
    if bash is None:
        out["reason"] = "bash not found on PATH"
        return out
    if STOP.is_set():
        out["reason"] = "runner stopped by a signal before this command started"
        return out
    env = dict(os.environ)
    env.update(env_extra)
    started_at = time.monotonic()
    rc, timed_out, started, note = spawn_and_wait([bash, "-c", cmd], ctx.root, log, timeout,
                                                  ctx.grace, env=env)
    out["seconds"] = round(time.monotonic() - started_at, 1)
    out["rc"] = rc
    state, reason = classify(rc, timed_out, started)
    if note:
        reason = note
    if STOP.is_set() and state != PASS:
        state, reason = CNT, f"runner stopped by a signal while this ran ({reason})"
    out["state"], out["reason"] = state, reason
    return out


def _fold(record: dict) -> None:
    """A record's state from its commands: FAIL and COULD-NOT-TELL dominate, then
    a command that did not run (SKIP) makes the whole NOT VERIFIED; PASS needs
    every command PASS."""
    states = [c["state"] for c in record["commands"]]
    for want in (FAIL, CNT, SKIP):
        if want in states:
            bad = next(c for c in record["commands"] if c["state"] == want)
            record["state"] = want
            record["rc"] = bad["rc"]
            record["reason"] = f"{bad['cmd'][:80]}: {bad['reason']}" if bad["reason"] else bad["cmd"][:80]
            return
    record["state"], record["rc"] = PASS, 0


def tree_dirty_now(ctx: Context):
    """True/False/None (could not tell) for the working tree right now. Paths
    under this run's own --out are the runner's logs, not the tree's change."""
    porcelain = _git(ctx.root, "status", "--porcelain", "-z")
    if porcelain is None:
        return None
    try:
        rel = os.path.relpath(ctx.out, ctx.root).replace(os.sep, "/")
    except ValueError:
        rel = None
    own = rel is not None and rel != "." and not rel.startswith("..")
    for tok in porcelain.split("\0"):
        if not tok:
            continue
        path = tok[3:] if len(tok) > 3 else tok
        if own and (path == rel or path.startswith(rel.rstrip("/") + "/")):
            continue
        return True
    return False


def run_member(spec: dict, unit_id: str, ctx: Context) -> dict:
    rec = _record(spec["id"], unit_id)
    if spec["fail_paths"] is not None:
        rec["state"], rec["rc"] = FAIL, None
        rec["reason"] = (f"unmapped={spec.get('fail_value')!r}: no rule maps " +
                         ", ".join(spec["fail_paths"]))
        return rec
    if spec["exclusion"]:
        rec["state"] = SKIP
        rec["reason"] = f"NOT VERIFIED - {spec['exclusion'][0]}: {spec['exclusion'][1]}"
        return rec
    if spec["requires_clean_tree"]:
        dirty = tree_dirty_now(ctx)  # sampled now: an earlier rule may have dirtied it
        if dirty is None:
            rec["state"], rec["reason"] = CNT, "could not tell whether the working tree is clean"
            return rec
        if dirty:
            rec["state"], rec["reason"] = SKIP, "NOT VERIFIED - requires a clean working tree"
            return rec
    if not spec["commands"]:
        rec["state"], rec["reason"] = SKIP, "NOT VERIFIED - the rule has no runnable command"
        return rec
    excl = spec.get("command_exclusions") or [None] * len(spec["commands"])
    for k, cmd in enumerate(spec["commands"]):
        if excl[k]:
            rec["commands"].append({"cmd": cmd, "rc": None, "state": SKIP, "log": None,
                                    "seconds": 0.0,
                                    "reason": f"NOT VERIFIED - {excl[k][0]}: {excl[k][1]}"})
            continue
        log = os.path.join(ctx.out, "logs", f"{_safe(unit_id)}-{_safe(spec['id'])}-{k}.log")
        res = _run_command(cmd, spec["env"], spec["timeout"], log, ctx)
        rec["commands"].append(res)
        rec["seconds"] = round(rec["seconds"] + res["seconds"], 1)
        if res["state"] != PASS:
            break
    _fold(rec)
    return rec


def run_unit(unit: dict, ctx: Context) -> list:
    """The records of one unit, superset first. A subset is credited only when,
    in this same run, the superset is PASS, PYTEST_ADDOPTS is empty and the tree
    snapshots taken before the superset and before the credit are equal (D8)."""
    specs = unit["specs"]
    records = []
    subsets = [s for s in specs if s["credit_to"]]
    vr = ctx.helpers.vr if ctx.helpers else None
    snap0 = vr.tree_snapshot(ctx.root) if (vr is not None and subsets) else None
    sup = run_member(specs[0], unit["id"], ctx)
    records.append(sup)
    snap1 = vr.tree_snapshot(ctx.root) if (vr is not None and subsets) else None
    credit = (sup["state"] == PASS and not os.environ.get("PYTEST_ADDOPTS", "")
              and snap0 is not None and snap0 == snap1)
    for spec in specs[1:]:
        # A credit never outranks the subset's own exclusions (D6/D10): a reach
        # exclusion or a tree that is not known clean sends it to run_member,
        # which records SKIP / COULD-NOT-TELL instead of a PASS.
        blocked = bool(spec["exclusion"]) or (
            spec["requires_clean_tree"] and tree_dirty_now(ctx) is not False)
        if credit and spec["credit_to"] and not blocked:
            rec = _record(spec["id"], unit["id"])
            rec["state"], rec["rc"], rec["credited_by"] = PASS, None, spec["credit_to"]
            rec["reason"] = f"covered by {spec['credit_to']}, PASS this run"
            records.append(rec)
        else:
            records.append(run_member(spec, unit["id"], ctx))
    return records


def _unit_valid(unit: dict, res) -> bool:
    """A heavy-part unit result is taken only under its own unit id, with one
    record per member (no extras), each record's state one its rc can give."""
    if not isinstance(res, dict) or res.get("unit") != unit["id"] \
            or not isinstance(res.get("records"), list):
        return False
    want = {s["id"]: s for s in unit["specs"]}
    seen = {}
    for rec in res["records"]:
        if not isinstance(rec, dict) or not all(k in rec for k in ("id", "state", "rc", "unit")):
            return False
        if rec["id"] not in want or rec["id"] in seen or rec["unit"] != unit["id"]:
            return False
        seen[rec["id"]] = rec
    if set(seen) != set(want):
        return False
    for rid, rec in seen.items():
        rc, state = rec["rc"], rec["state"]
        if state not in (PASS, FAIL, SKIP, CNT):
            return False
        if rc is not None and (isinstance(rc, bool) or not isinstance(rc, int)):
            return False
        if state == PASS:
            if rc == 0:
                continue
            sup = seen.get(unit["id"])
            owner = want[rid]["credit_to"]
            if not (rc is None and owner is not None and rec.get("credited_by") == owner
                    and sup is not None and sup["state"] == PASS):
                return False
        elif state == FAIL:
            if rc is None or classify(rc, False, True)[0] != FAIL:
                if not (rc is None and want[rid]["fail_paths"] is not None):
                    return False
        elif state == SKIP and not (rc is None or rc == EXIT_SKIP):
            return False
    return True


def run_map_inner(part: str, plan_file: str, digest: str, ctx: Context) -> int:
    """The units inside the one heavy-run call, serially. Refuses (exit 2, nothing
    run) unless the plan file has the digest the outer runner computed."""
    try:
        with open(plan_file, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise Refusal(f"--plan-file {plan_file}: {exc}") from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        raise Refusal("--map-inner: the plan file changed since the outer runner wrote it "
                      f"(outer {digest}, inner {hashlib.sha256(raw).hexdigest()})")
    plan = json.loads(raw.decode("utf-8"))
    ctx.tree_dirty = plan.get("tree_dirty")
    ctx.helpers = load_helpers(ctx.root)
    data = {"started": time.time(), "pid": os.getpid(), "nonce": plan.get("nonce"),
            "slot": os.environ.get("HEAVY_RUN_SLOT") or None, "units": {}}
    write_status(part, data)
    for unit in plan["units"]:
        data["units"][unit["id"]] = {"unit": unit["id"], "records": run_unit(unit, ctx)}
        write_status(part, data)
    if STOP.is_set():
        return 128 + (STOP_SIGNAL[0] if STOP_SIGNAL else int(signal.SIGTERM))
    return 0


def _tail_lines(path, count: int = 20) -> list:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 65536))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return []
    return [ln for ln in lines if ln.strip()][-count:]


def record_line(rec: dict) -> str:
    base = f"{rec['state']} {rec['id']} rc={rec['rc']} secs={rec['seconds']}"
    return f"{base} -- {rec['reason']}" if rec["reason"] else base


def map_last_line(results: list, plan: dict, state: str, hr_label: str, workers: tuple,
                  status_path: str) -> str:
    credited = [r for r in results if r.get("credited_by")]
    skipped = [r["id"] for r in results if r["state"] == SKIP]
    ran = [r for r in results if r["state"] != SKIP and not r.get("credited_by")]
    return (f"overall: {state}  ran {len(ran)}, credited {len(credited)}, "
            f"other_tier {len(plan['other_tier'])}, SKIPPED {len(skipped)} "
            f"(NOT VERIFIED: {', '.join(skipped) or 'none'}), carried {len(plan['carried'])}  "
            f"workers: {workers[0]} ({workers[1]})  heavy_run: {hr_label}  status: {status_path}")


def run_map(args) -> int:
    root = os.path.abspath(args.root)
    plan = build_plan(args, root)
    if args.plan:
        print(json.dumps(plan_json(plan), indent=2))
        return EXIT_PASS
    mode, hpath = resolve_heavy_run(os.environ)
    install_signal_handlers()
    if args.workers:
        workers = (args.workers, "flag", f"--workers {args.workers}")
    else:
        workers = probe_workers()
    print(f"workers: {workers[0]} ({workers[1]}: {workers[2]})", file=sys.stderr)
    for note in plan["notices"]:
        print(note, file=sys.stderr)
    out = os.path.abspath(args.out) if args.out else default_out(root)
    ctx = Context(root, out, args.grace, set())
    ctx.helpers = plan["helpers"]
    porcelain = _git(root, "status", "--porcelain")
    ctx.tree_dirty = (porcelain.strip() != "") if porcelain is not None else None
    hr = {"mode": mode, "path": hpath, "launched": False, "rc": None, "waited_seconds": None,
          "slot": None, "note": "uncapped" if mode == "absent" else None}
    status_path = os.path.join(out, "status.json")
    status = {
        "runner": "scripts/gate-runner.py", "root": root, "head": plan["head"],
        "dirty": ctx.tree_dirty, "heavy_run": hr,
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ended": None,
        "overall": "RUNNING", "steps": [],
        "map": {"mode": plan_json(plan)["mode"], "tier": plan["tier"],
                "slice": f"{plan['slice_k']}/{plan['n']}" if plan["slice_k"] else None,
                "head": plan["head"], "changed_digest": plan["changed_digest"],
                "map_digest": plan["map_digest"], "partition_digest": plan["partition_digest"],
                "workers": {"n": workers[0], "source": workers[1], "why": workers[2]},
                "units": plan_json(plan)["units"], "other_tier": plan["other_tier"],
                "carried": plan["carried"], "notices": plan["notices"]}}
    by_unit: dict = {}
    lock = threading.Lock()

    def save() -> None:
        flat = []
        for unit in plan["run_units"]:
            flat.extend(by_unit.get(unit["id"], []))
        status["steps"] = flat
        with lock:
            write_status(status_path, status)

    to_run = [u for u in plan["run_units"] if u["id"] != "@unmapped"]
    for unit in plan["run_units"]:
        if unit["id"] == "@unmapped":
            by_unit[unit["id"]] = [run_member(unit["specs"][0], unit["id"], ctx)]
    if plan["slice_k"]:
        direct, heavy = [], to_run
    else:
        direct = [u for u in to_run if u["tier"] == "fast"]
        heavy = [u for u in to_run if u["tier"] != "fast"]
    save()
    if direct:
        queue = list(direct)
        qlock = threading.Lock()

        def worker() -> None:
            while True:
                with qlock:
                    if not queue:
                        return
                    unit = queue.pop(0)
                try:
                    by_unit[unit["id"]] = run_unit(unit, ctx)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    by_unit[unit["id"]] = _cnt_records(unit, f"worker raised {type(exc).__name__}: {exc}")
                save()

        threads = [threading.Thread(target=worker) for _ in range(min(workers[0], len(direct)))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    if heavy and mode == "absent":
        for unit in heavy:
            by_unit[unit["id"]] = run_unit(unit, ctx)
            save()
    elif heavy:
        _run_heavy(args, plan, heavy, ctx, hr, by_unit, save)
    for unit in plan["run_units"]:  # a unit with no result is never a silent PASS
        if unit["id"] not in by_unit:
            by_unit[unit["id"]] = _cnt_records(unit, "no result was recorded for this unit")
    save()
    results = [r for u in plan["run_units"] for r in by_unit.get(u["id"], [])]
    state, code = overall(results)
    status["overall"] = state
    status["ended"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save()
    last = map_last_line(results, plan, state, heavy_run_label(hr), workers, status_path)
    if state == PASS:
        print(last)
        return code
    for rec in results:
        if rec["state"] in (FAIL, CNT):
            print(record_line(rec))
            for cmd in rec["commands"]:
                if cmd["state"] in (FAIL, CNT):
                    for line in _tail_lines(cmd["log"]):
                        print(f"  | {line}")
    print(last)
    return code


def _cnt_records(unit: dict, why: str) -> list:
    recs = []
    for spec in unit["specs"]:
        rec = _record(spec["id"], unit["id"])
        rec["state"], rec["reason"] = CNT, why
        recs.append(rec)
    return recs


def _run_heavy(args, plan: dict, heavy: list, ctx: Context, hr: dict, by_unit: dict, save) -> None:
    plan_file = os.path.join(ctx.out, "plan.json")
    nonce = uuid.uuid4().hex
    part = os.path.join(ctx.out, "heavy-part.json")
    try:
        os.remove(part)  # a result left by an earlier run in this --out is not this run's
    except FileNotFoundError:
        pass
    write_status(plan_file, {"tree_dirty": ctx.tree_dirty, "nonce": nonce, "units": heavy})
    with open(plan_file, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    cmd = [sys.executable, os.path.abspath(__file__), "--map-inner", part, "--plan-file",
           plan_file, "--plan-digest", digest, "--root", ctx.root, "--out", ctx.out,
           "--grace", f"{ctx.grace:g}"]
    cmd = [hr["path"], *cmd]
    wanted = {u["id"]: u for u in heavy}

    def take_part() -> dict:
        got = read_json(part)
        units = got.get("units") if isinstance(got, dict) else None
        if not isinstance(units, dict) or got.get("nonce") != nonce:
            return {}, None, None
        good = {uid: res["records"] for uid, res in units.items()
                if uid in wanted and _unit_valid(wanted[uid], res)}
        started = got.get("started")
        if isinstance(started, bool) or not isinstance(started, (int, float)) \
                or not math.isfinite(started):
            started = None
        return good, started, _slot(got.get("slot"))

    def tick() -> None:
        fresh = {uid: recs for uid, recs in take_part()[0].items() if uid not in by_unit}
        if fresh:
            by_unit.update(fresh)
            save()

    budget = args.heavy_timeout or (sum(u["timeout"] for u in heavy) + ctx.grace * (len(heavy) + 2)
                                    + SLOT_WAIT_ALLOWANCE)
    launched = time.time()
    hr["launched"] = True
    save()
    if STOP.is_set():
        rc, timed_out, note = None, False, "runner stopped by a signal before the heavy-run call"
    else:
        rc, timed_out, _s, note = spawn_and_wait(
            cmd, ctx.root, os.path.join(ctx.out, "logs", "heavy-run.log"), budget,
            ctx.grace * 2 + 5, on_tick=tick)
    hr["rc"] = rc
    recorded, inner_started, hr["slot"] = take_part()
    if inner_started is not None:
        hr["waited_seconds"] = round(inner_started - launched, 1)
    why = (f"heavy-run call timed out after {budget:g}s (slot wait included)" if timed_out
           else note or f"heavy-run call ended rc={rc}")
    if rc == EXIT_USAGE and not timed_out and not note:
        tail = _log_tail(os.path.join(ctx.out, "logs", "heavy-run.log"))
        if tail:
            why = f"{why} ({tail})"
    for unit in heavy:
        if unit["id"] in recorded:
            by_unit[unit["id"]] = recorded[unit["id"]]
        elif unit["id"] not in by_unit:
            by_unit[unit["id"]] = _cnt_records(unit, f"{why} before this unit recorded a result")
    save()


# ---- main -----------------------------------------------------------------

def _duration(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from exc
    if not positive_finite(value):
        raise argparse.ArgumentTypeError(f"{text!r} must be a finite number > 0")
    return value


def _workers(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from exc
    if not 1 <= value <= 8:
        raise argparse.ArgumentTypeError(f"{text!r} must be 1..8")
    return value


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Run this repository's whole local gate.")
    ap.add_argument("--root", default=DEFAULT_ROOT, help="repository root (default: this repo)")
    ap.add_argument("--out", help="status/log directory (default $TMPDIR/gate-runner/<sha>-<utc>)")
    ap.add_argument("--list", action="store_true", help="print the step table and exit")
    ap.add_argument("--check-ci", action="store_true", help="check the table against CI and exit")
    ap.add_argument("--skip", action="append", metavar="NAME", help="record NAME as SKIP, do not run it")
    ap.add_argument("--only", action="append", metavar="NAME", help="run only NAME (repeatable)")
    ap.add_argument("--table", help="a JSON step table instead of the built-in one (tests, ad-hoc)")
    ap.add_argument("--grace", type=_duration, default=30.0, help="seconds between SIGTERM and SIGKILL")
    ap.add_argument("--heavy-timeout", type=_duration, default=None,
                    help="seconds for the whole heavy-run call (default: from the step timeouts)")
    ap.add_argument("--map", help="map mode: select, tier and slice the rules of this verify.json "
                    "(relative to --root); see the module docstring")
    ap.add_argument("--changed-file", metavar="PATH", help="map mode: newline list of changed paths (- = stdin)")
    ap.add_argument("--base", metavar="REF", help="map mode: changed = git diff REF...HEAD plus dirty paths")
    ap.add_argument("--tier", choices=("fast", "heavy", "all"), help="map mode: run one tier")
    ap.add_argument("--slice", metavar="K/N", help="map mode: run slice K of N of the whole selected set")
    ap.add_argument("--fast-seconds", type=_duration, default=None,
                    help=f"map mode: measured seconds below which a rule is fast (default {DEFAULT_FAST_SECONDS})")
    ap.add_argument("--workers", type=_workers, default=None,
                    help="map mode: direct fast-tier concurrency, 1..8 (default: probed)")
    ap.add_argument("--plan", action="store_true", help="map mode: print the selection as JSON, run nothing")
    ap.add_argument("--inner", metavar="PART_JSON", help=argparse.SUPPRESS)
    ap.add_argument("--table-digest", help=argparse.SUPPRESS)
    ap.add_argument("--map-inner", metavar="PART_JSON", help=argparse.SUPPRESS)
    ap.add_argument("--plan-file", help=argparse.SUPPRESS)
    ap.add_argument("--plan-digest", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.map_inner:
            if not (args.plan_file and args.plan_digest and args.out):
                raise Refusal("--map-inner needs --plan-file, --plan-digest and --out")
            install_signal_handlers()
            ctx = Context(os.path.abspath(args.root), os.path.abspath(args.out), args.grace, set())
            return run_map_inner(args.map_inner, args.plan_file, args.plan_digest, ctx)
        map_flags = [name for name, val in (
            ("--tier", args.tier), ("--slice", args.slice), ("--changed-file", args.changed_file),
            ("--base", args.base), ("--plan", args.plan), ("--workers", args.workers),
            ("--fast-seconds", args.fast_seconds)) if val]
        if map_flags and not args.map:
            raise Refusal(f"{', '.join(map_flags)} need --map")
        if args.map:
            clash = [name for name, val in (("--table", args.table), ("--list", args.list),
                                            ("--check-ci", args.check_ci), ("--only", args.only),
                                            ("--skip", args.skip), ("--inner", args.inner)) if val]
            if clash:
                raise Refusal(f"--map cannot be combined with {', '.join(clash)}")
            if args.tier and args.slice:
                raise Refusal("--tier and --slice are exclusive")
            if bool(args.changed_file) == bool(args.base):
                raise Refusal("map mode needs exactly one of --changed-file and --base")
            args.fast_seconds = args.fast_seconds or DEFAULT_FAST_SECONDS
            return run_map(args)
        steps, source = load_table(args.table, os.path.abspath(args.root))
        digest = table_digest(steps)  # the full table, before --only
        if args.inner and args.table_digest != digest:
            raise Refusal("--inner: table changed since the outer runner validated it "
                          f"(outer {args.table_digest or 'none given'}, inner {digest})"
                          if args.table_digest else
                          "--inner needs --table-digest (no unchecked table is run)")
        names = {s.name for s in steps}
        unknown = sorted(set(args.skip or ()) - names) + sorted(set(args.only or ()) - names)
        if unknown:
            raise Refusal(f"unknown step name(s): {', '.join(unknown)} (see --list)")
        if args.only:
            steps = [s for s in steps if s.name in set(args.only)]
        if args.list:
            print_list(steps)
            return EXIT_PASS
        if args.check_ci:
            try:
                import yaml  # noqa: F401  pylint: disable=unused-import
            except ImportError:
                print("gate-runner --check-ci: pyyaml not importable; NOT VERIFIED")
                return EXIT_SKIP
            problems = ci_drift(os.path.abspath(args.root), steps)
            for problem in problems:
                print(f"DRIFT {problem}")
            print(f"gate-runner --check-ci: {len(problems)} problem(s)")
            return EXIT_FAIL if problems else EXIT_PASS
        root = os.path.abspath(args.root)
        install_signal_handlers()
        if args.inner:
            ctx = Context(root, os.path.abspath(args.out), args.grace, set(args.skip or ()))
            return run_inner(args.inner, [s for s in steps if s.phase != "cheap"], ctx)
        mode, path = resolve_heavy_run(os.environ)
    except Refusal as exc:
        print(f"gate-runner: {exc}", file=sys.stderr)
        return EXIT_USAGE
    out = os.path.abspath(args.out) if args.out else default_out(root)
    ctx = Context(root, out, args.grace, set(args.skip or ()))
    hr = {"mode": mode, "path": path, "launched": False, "rc": None, "waited_seconds": None,
          "slot": None, "note": "uncapped" if mode == "absent" else None}
    return run_outer(args, steps, source, ctx, hr, digest)


if __name__ == "__main__":
    sys.exit(main())
